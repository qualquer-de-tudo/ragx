"""Fase 13 — Task Analyzer e orquestração.

Os oito cenários obrigatórios da §35 do pedido estão marcados com `[§35]` no
nome. Eles são o critério de que o sistema não só roda, mas roda certo quando
algo dá errado.
"""

from __future__ import annotations

import itertools
import threading
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.tasks import serialize as task_serialize
from ragx.tasks import service
from ragx.tasks.analyzer import analyze, override
from ragx.tasks.dispatcher import TaskDispatcher, validate
from ragx.tasks.models import (
    Classification,
    CycleError,
    DependencyKind,
    InvalidTransitionError,
    Status,
    Task,
    TaskResult,
    merge_status,
)
from ragx.tasks.store import TaskRepository, db_path, open_tasks_db
from ragx.tasks.worker import cron_next, parse_cron, work

pytestmark = pytest.mark.integration

SEGREDO = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    raiz = tmp_path / "proj"
    (raiz / "src").mkdir(parents=True)
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n\n'
        f'[hub]\npath = "{(home / ".ragx" / "hub").as_posix()}"\n\n'
        "[tasks]\nlease_seconds = 2\nmax_retries = 2\nbackoff = [0, 0, 0]\n",
        encoding="utf-8",
    )
    (raiz / "src" / "auth.py").write_text(
        "class AuthService:\n    def login(self, c):\n        return c\n",
        encoding="utf-8",
    )
    (raiz / "src" / "billing.py").write_text(
        "class InvoiceService:\n    def total(self, i):\n        return 0\n",
        encoding="utf-8",
    )
    (raiz / ".env").write_text(SEGREDO + "\n", encoding="utf-8")
    c = load_config(raiz)
    index_project(c)
    return c


@pytest.fixture
def repo(cfg):
    with open_tasks_db(cfg) as conn:
        yield TaskRepository(conn)


def _task(repo: TaskRepository, tid: str, projeto: str = "P", **kw) -> str:
    if repo.get_project(projeto) is None:
        repo.create_project(projeto, "proj", "pedido", {})
    campos = {
        "id": tid, "project_id": projeto, "seq": int(tid[-1] or 1),
        "title": f"Tarefa {tid}",
        "acceptance_criteria": ["feito"],
    }
    campos.update(kw)
    return repo.create_task(Task(**campos))


# ── §35: classificação ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [
        ("Corrigir typo na descricao do produto", Classification.DIRECT_EXECUTION),
        ("Mudar o texto do botao de salvar", Classification.DIRECT_EXECUTION),
        ("Renomear a variavel tmp para buffer", Classification.DIRECT_EXECUTION),
        ("Ajustar o espacamento do menu lateral", Classification.DIRECT_EXECUTION),
    ],
)
def test_solicitacao_simples_nao_cria_burocracia_35(cfg, pedido, esperado) -> None:
    """[§35] Pedido simples não vira projeto.

    Metade do valor está aqui: uma ferramenta que transforma typo em board de
    doze tarefas é desligada na primeira semana.
    """
    a = analyze(cfg, pedido)
    assert a.classification is esperado, a.reasoning_summary
    assert not a.requires_documentation
    p = service.plan_work(cfg, pedido, apply=False)
    assert p.tasks == []


def test_solicitacao_complexa_documenta_antes_35(cfg) -> None:
    """[§35] Pedido complexo documenta e decompõe antes de executar."""
    a = analyze(
        cfg,
        "Implementar novo modulo de assinaturas com cobranca recorrente, "
        "integracao com gateway e nova tabela de planos",
    )
    assert a.requires_documentation
    assert a.requires_decomposition
    assert "DOCUMENT" in a.strategy and "DECOMPOSE" in a.strategy

    p = service.plan_work(cfg, a.request, apply=False)
    assert len(p.tasks) >= 6
    assert p.documents
    assert all(t["acceptance_criteria"] for t in p.tasks)


def test_seguranca_nunca_e_execucao_direta(cfg) -> None:
    """Autenticação, autorização e dado pessoal não são 'faz agora'."""
    for pedido in (
        "Alterar a autenticacao para OAuth",
        "Mudar as permissoes de acesso do relatorio",
        "Armazenar o CPF do cliente no cadastro",
        "Rotacionar a chave de api do gateway",
    ):
        a = analyze(cfg, pedido)
        assert a.classification is not Classification.DIRECT_EXECUTION, pedido


def test_classificacao_e_deterministica(cfg) -> None:
    pedido = "Migrar o banco de MySQL para Postgres"
    resultados = {analyze(cfg, pedido).to_dict()["classification"] for _ in range(8)}
    assert len(resultados) == 1


def test_sobreposicao_exige_justificativa(cfg) -> None:
    a = analyze(cfg, "Corrigir typo")
    with pytest.raises(ValueError):
        override(a, "DOCUMENTATION_REQUIRED", "agente", "  ")
    override(a, "DOCUMENTATION_REQUIRED", "agente", "toca contrato externo")
    assert a.overridden_by == "agente"
    assert a.requires_documentation


# ── §35: dependências e DAG ─────────────────────────────────────────────
def test_dependencia_incompleta_nao_executa_35(repo) -> None:
    """[§35] Tarefa com dependência aberta não fica pronta."""
    _task(repo, "T1")
    _task(repo, "T2")
    repo.add_dependency("T2", "T1")
    prontas = {t["id"] for t in repo.ready_tasks()}
    assert "T1" in prontas
    assert "T2" not in prontas


def test_dependencia_concluida_libera_a_proxima_35(repo) -> None:
    """[§35] Dependência satisfeita libera a dependente."""
    _task(repo, "T1")
    _task(repo, "T2")
    repo.add_dependency("T2", "T1")
    repo.set_status("T1", Status.READY)
    repo.set_status("T1", Status.QUEUED)
    repo.set_status("T1", Status.RUNNING)
    repo.set_status("T1", Status.COMPLETED)
    assert "T2" in {t["id"] for t in repo.ready_tasks()}
    assert "T2" in repo.promote_ready()


def test_tarefa_bloqueada_nao_executa_35(repo) -> None:
    """[§35] Tarefa bloqueada fica fora da fila."""
    _task(repo, "T1")
    repo.set_status("T1", Status.BLOCKED)
    assert "T1" not in {t["id"] for t in repo.ready_tasks()}


@pytest.mark.parametrize("tamanho", [2, 3])
def test_ciclo_e_recusado_na_criacao(repo, tamanho: int) -> None:
    ids = [f"T{i}" for i in range(1, tamanho + 1)]
    for tid in ids:
        _task(repo, tid)
    for a, b in itertools.pairwise(ids):
        repo.add_dependency(b, a)
    with pytest.raises(CycleError) as exc:
        repo.add_dependency(ids[0], ids[-1])
    assert ids[0] in exc.value.caminho


def test_auto_dependencia_e_recusada(repo) -> None:
    _task(repo, "T1")
    with pytest.raises(CycleError):
        repo.add_dependency("T1", "T1")


def test_tarefa_sem_criterio_de_aceite_e_recusada(repo) -> None:
    """Sem critério, `completed` não significa nada e a validação não tem o que ver."""
    with pytest.raises(ValueError, match="critério de aceite"):
        _task(repo, "T1", acceptance_criteria=[])


def test_transicao_invalida_e_recusada(repo) -> None:
    _task(repo, "T1")
    repo.set_status("T1", Status.READY)
    repo.set_status("T1", Status.QUEUED)
    repo.set_status("T1", Status.RUNNING)
    repo.set_status("T1", Status.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        repo.set_status("T1", Status.RUNNING)


# ── §35: concorrência ───────────────────────────────────────────────────
def test_worker_duplicado_nao_executa_a_mesma_tarefa_35(cfg) -> None:
    """[§35] Threads reais disputando: exatamente um vencedor.

    `SELECT` seguido de `UPDATE` perde esta corrida — entre os dois, outro
    processo passa. O teste existe porque o bug não aparece em
    desenvolvimento, só em produção sob carga.
    """
    with open_tasks_db(cfg) as conn:
        _task(TaskRepository(conn), "T1")
        TaskRepository(conn).set_status("T1", Status.READY)

    vencedores: list[str] = []
    trava = threading.Lock()
    partida = threading.Event()

    def tenta(n: int) -> None:
        partida.wait()
        with open_tasks_db(cfg) as conn:
            got = TaskRepository(conn).claim("T1", f"w{n}", 60)
        if got is not None:
            with trava:
                vencedores.append(f"w{n}")

    threads = [threading.Thread(target=tenta, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    partida.set()
    for t in threads:
        t.join(timeout=30)

    assert len(vencedores) == 1, f"esperava 1 vencedor, veio {vencedores}"


def test_lease_vencido_e_recuperado(cfg, repo) -> None:
    """Agente que morre no meio não trava a fila para sempre."""
    _task(repo, "T1")
    repo.set_status("T1", Status.READY)
    assert repo.claim("T1", "morto", lease_seconds=-5) is not None
    assert repo.get("T1")["status"] == str(Status.QUEUED)

    recuperadas = repo.expire_leases()
    assert "T1" in recuperadas
    assert repo.get("T1")["status"] == str(Status.READY)
    assert any(e["type"] == "LEASE_EXPIRED" for e in repo.events("T1"))


# ── §35: retry ──────────────────────────────────────────────────────────
def test_tarefa_falha_faz_retry_conforme_politica_35(cfg, repo) -> None:
    """[§35] Retry segue a política e PARA. Nunca é infinito."""
    _task(repo, "T1", max_retries=2)
    backoff = [0, 0, 0]
    assert repo.schedule_retry("T1", backoff, "erro 1") is True
    assert repo.get("T1")["retry_count"] == 1
    assert repo.schedule_retry("T1", backoff, "erro 2") is True
    assert repo.get("T1")["retry_count"] == 2
    assert repo.schedule_retry("T1", backoff, "erro 3") is False
    assert repo.get("T1")["retry_count"] == 2
    assert "erro 3" in repo.get("T1")["last_error"]


# ── §35: segredo ────────────────────────────────────────────────────────
def test_segredo_nao_chega_ao_agente_35(cfg) -> None:
    """[§35] O contexto entregue ao agente não contém segredo.

    O `.env` foi bloqueado pelo gate antes do parser, então não está no
    índice — e o contexto vem do índice, não do disco.
    """
    p = service.plan_work(
        cfg, "Alterar a autenticacao do AuthService para usar chave de api", apply=True
    )
    assert p.tasks

    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        d = TaskDispatcher(cfg, repo, "t").claim()
        assert d is not None
        assert "wJalrXUtnFEMI" not in d.context
        assert "AWS_SECRET_ACCESS_KEY" not in d.context
        assert ".env" not in d.context


# ── validação ───────────────────────────────────────────────────────────
def test_resultado_fora_de_escopo_e_recusado(cfg, repo) -> None:
    _task(repo, "T1", files_scope=["src"], acceptance_criteria=["feito"])
    tarefa = repo.get("T1")
    v = validate(cfg, tarefa, TaskResult(
        summary="ok", files_changed=["/etc/passwd", "src/auth.py"],
        acceptance={"feito": "linha 12"},
    ))
    assert not v.ok
    assert any("fora do escopo" in f for f in v.failures)


def test_criterio_sem_evidencia_e_recusado(cfg, repo) -> None:
    _task(repo, "T1", acceptance_criteria=["teste passa", "doc atualizado"])
    v = validate(cfg, repo.get("T1"), TaskResult(summary="feito"))
    assert not v.ok
    assert any("sem evidência" in f for f in v.failures)


def test_teste_exigido_e_ausente_e_recusado(cfg, repo) -> None:
    _task(repo, "T1", test_requirements=["suite verde"])
    v = validate(cfg, repo.get("T1"), TaskResult(
        summary="ok", acceptance={"feito": "sim"}
    ))
    assert not v.ok
    assert any("exige teste" in f for f in v.failures)


def test_resultado_valido_conclui_e_libera(cfg) -> None:
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        _task(repo, "T1")
        _task(repo, "T2")
        repo.add_dependency("T2", "T1")
        repo.set_status("T1", Status.READY)

        disp = TaskDispatcher(cfg, repo, "t")
        d = disp.claim("T1")
        assert d is not None
        v, estado = disp.report("T1", {
            "status": "completed", "summary": "pronto",
            "acceptance": {"feito": "evidência"},
        })
        assert v.ok, v.failures
        assert estado["status"] == "completed"
        assert "T2" in estado["unblocked"]


def test_resultado_invalido_vai_para_retry(cfg) -> None:
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        _task(repo, "T1", max_retries=1)
        repo.set_status("T1", Status.READY)
        disp = TaskDispatcher(cfg, repo, "t")
        assert disp.claim("T1") is not None
        v, estado = disp.report("T1", {"status": "completed", "summary": ""})
        assert not v.ok
        assert estado["status"] == "retrying"


def test_decisao_da_tarefa_alimenta_a_proxima(cfg) -> None:
    """O feedback loop: o que a T1 descobriu chega na T2 sem ninguém contar."""
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        _task(repo, "T1")
        _task(repo, "T2")
        repo.add_dependency("T2", "T1")
        repo.set_status("T1", Status.READY)

        disp = TaskDispatcher(cfg, repo, "t")
        disp.claim("T1")
        disp.report("T1", {
            "status": "completed", "summary": "mapeado",
            "acceptance": {"feito": "ok"},
            "decisions": [{"title": "Reusar o gateway existente",
                           "decision": "nao criar cliente novo"}],
        })
        d2 = disp.claim("T2")
        assert d2 is not None
        assert "Reusar o gateway existente" in d2.context


# ── worker e cron ───────────────────────────────────────────────────────
def test_worker_nao_executa_tarefa(cfg) -> None:
    """O worker mantém a fila. Quem executa é o agente (ADR-0015)."""
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        _task(repo, "T1")
    r = work(cfg)
    assert "T1" in r.promoted
    with open_tasks_db(cfg, read_only=True) as conn:
        assert TaskRepository(conn).get("T1")["status"] == str(Status.READY)


def test_worker_e_idempotente(cfg) -> None:
    with open_tasks_db(cfg) as conn:
        _task(TaskRepository(conn), "T1")
    primeiro = work(cfg)
    segundo = work(cfg)
    assert primeiro.changed >= 1
    assert segundo.changed == 0


def test_worker_nao_morre_com_erro_em_um_passo(cfg, monkeypatch) -> None:
    import ragx.tasks.worker as wk

    monkeypatch.setattr(
        wk, "_fire_schedules", lambda repo: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        _task(repo, "T1")
        r = wk.run_cycle(cfg, repo)
    assert any("boom" in e for e in r.errors)
    assert "T1" in r.promoted  # o resto do ciclo aconteceu


@pytest.mark.parametrize(
    "expr",
    ["*/5 * * * *", "0 * * * *", "0 2 * * *", "30 3 1 * *", "0 0 * * 0",
     "*/15 9-18 * * 1-5", "1,2,3 * * * *", "0 */6 * * *"],
)
def test_cron_valido(expr: str) -> None:
    assert parse_cron(expr)
    assert cron_next(expr) is not None


@pytest.mark.parametrize(
    "expr", ["", "* * * *", "* * * * * *", "99 * * * *", "*/0 * * * *", "a * * * *"]
)
def test_cron_invalido_e_recusado(expr: str) -> None:
    with pytest.raises(ValueError):
        parse_cron(expr)


# ── versionamento ───────────────────────────────────────────────────────
def test_board_viaja_no_git_e_execucao_nao(cfg) -> None:
    """A definição do trabalho é versionada; a execução, não (ADR-0014)."""
    service.plan_work(cfg, "Implementar novo modulo de cobranca recorrente", apply=True)
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        alvo = repo.ready_tasks()[0]["id"]
        repo.set_status(alvo, Status.QUEUED)
        repo.start_run(alvo, "w", None, "h", 10)

    r = task_serialize.serialize(cfg)
    assert r.tasks >= 6
    pasta = cfg.knowledge_dir / "tasks"
    assert (pasta / "manifest.json").is_file()
    assert not (pasta / "runs").exists(), "execução não pode ser versionada"

    import json

    corpo = json.loads(
        next((pasta / "tasks").glob("*.json")).read_text(encoding="utf-8")
    )
    for proibido in ("locked_by", "lock_expires_at", "retry_count", "started_at"):
        assert proibido not in corpo, f"{proibido} vazou para o Git"


def test_serializacao_e_deterministica(cfg) -> None:
    service.plan_work(cfg, "Implementar novo modulo de cobranca", apply=True)
    task_serialize.serialize(cfg)
    arquivos = sorted((cfg.knowledge_dir / "tasks" / "tasks").glob("*.json"))
    antes = {p.name: p.read_bytes() for p in arquivos}
    r = task_serialize.serialize(cfg)
    depois = {p.name: p.read_bytes() for p in arquivos}
    assert antes == depois
    assert r.files_written == 0, "regravou sem mudança — o diff nunca ficaria vazio"


def test_reidratacao_reconstroi_o_board(cfg) -> None:
    service.plan_work(cfg, "Implementar novo modulo de cobranca", apply=True)
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        alvo = repo.ready_tasks()[0]["id"]
        repo.set_status(alvo, Status.READY)
        repo.set_status(alvo, Status.QUEUED)
        repo.set_status(alvo, Status.RUNNING)
        repo.set_status(alvo, Status.COMPLETED)
        antes = {t["id"]: t["status"] for t in repo.list_tasks()}
    task_serialize.serialize(cfg)

    db_path(cfg).unlink()  # simula `ragx reset`

    r = task_serialize.rehydrate(cfg)
    assert r.tasks == len(antes)
    assert r.history_lost is True, "perda de histórico precisa ser REPORTADA"
    with open_tasks_db(cfg, read_only=True) as conn:
        depois = {t["id"]: t["status"] for t in TaskRepository(conn).list_tasks()}
    assert depois[alvo] == str(Status.COMPLETED)
    assert set(depois) == set(antes)


def test_running_do_git_vira_pending_na_reidratacao(cfg) -> None:
    """Execução de outra máquina não vale para esta."""
    service.plan_work(cfg, "Implementar novo modulo de cobranca", apply=True)
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        alvo = repo.ready_tasks()[0]["id"]
        repo.set_status(alvo, Status.QUEUED)
        repo.set_status(alvo, Status.RUNNING)
    task_serialize.serialize(cfg)
    db_path(cfg).unlink()
    task_serialize.rehydrate(cfg)
    with open_tasks_db(cfg, read_only=True) as conn:
        voltou = TaskRepository(conn).get(alvo)["status"]
    # Vira `pending`; como não tem dependência aberta, o próprio `rehydrate`
    # já a promove a `ready`. O que importa é que NÃO voltou como em execução.
    assert voltou in (str(Status.PENDING), str(Status.READY)), voltou


@pytest.mark.parametrize(
    ("local", "remoto", "esperado"),
    [
        (Status.PENDING, Status.COMPLETED, Status.COMPLETED),
        (Status.COMPLETED, Status.PENDING, Status.COMPLETED),
        (Status.RUNNING, Status.FAILED, Status.FAILED),
        (Status.COMPLETED, Status.CANCELLED, Status.CANCELLED),
        (Status.CANCELLED, Status.COMPLETED, Status.CANCELLED),
        (Status.READY, Status.READY, Status.READY),
    ],
)
def test_precedencia_de_status_no_merge(local, remoto, esperado) -> None:
    assert merge_status(local, remoto) is esperado


# ── dois bancos ─────────────────────────────────────────────────────────
def test_orquestracao_usa_banco_proprio(cfg) -> None:
    """Separado do knowledge.db: VACUUM lá não pode travar o worker aqui."""
    with open_tasks_db(cfg) as conn:
        _task(TaskRepository(conn), "T1")
    assert db_path(cfg).name == "ragx.sqlite"
    assert db_path(cfg) != cfg.db_path
    assert db_path(cfg).exists() and cfg.db_path.exists()


def test_fila_nao_faz_n_mais_um(cfg) -> None:
    """500 tarefas com dependências não podem custar 501 consultas."""
    with open_tasks_db(cfg) as conn:
        repo = TaskRepository(conn)
        for i in range(1, 61):
            _task(repo, f"T{i:03d}", seq=i)
        for i in range(2, 61):
            repo.add_dependency(f"T{i:03d}", f"T{i-1:03d}")

        n = 0

        def contando(_sql: str) -> None:
            nonlocal n
            n += 1

        # `Connection.execute` é somente leitura; o trace callback é a forma
        # suportada de contar consultas de verdade.
        conn.set_trace_callback(contando)
        prontas = repo.ready_tasks(limit=100)
        conn.set_trace_callback(None)

    assert [t["id"] for t in prontas] == ["T001"]
    assert n <= 2, f"a fila fez {n} consultas — voltou o N+1"


def test_dependencia_related_to_nao_bloqueia(repo) -> None:
    _task(repo, "T1")
    _task(repo, "T2")
    repo.add_dependency("T2", "T1", DependencyKind.RELATED_TO)
    assert "T2" in {t["id"] for t in repo.ready_tasks()}
