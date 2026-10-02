"""Primeiro índice em paralelo (RAGX-0152): o resultado tem de ser IDÊNTICO ao do caminho sequencial."""

from __future__ import annotations

import multiprocessing
import shutil
import signal
import time
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import ClassVar

import pytest

from ragx.config import load_config
from ragx.indexing import parallel
from ragx.indexing.parallel import ParallelStats, WorkerError, process_stream, resolve_jobs
from ragx.indexing.pipeline import index_project
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db
from ragx.walk import Candidate, iter_candidates

pytestmark = pytest.mark.integration

N_MODULOS = 40
MAX_FILE_BYTES = 20_000


def _modulo(i: int) -> str:
    return (
        f'"""Módulo {i}."""\n\n\n'
        f"class Servico{i}:\n"
        f'    """Serviço {i}."""\n\n'
        f"    def executar(self, valor):\n"
        f'        """Executa o serviço {i}."""\n'
        f"        total = 0\n        for k in range(valor):\n            total += k * {i}\n"
        f"        return total\n\n\n"
        f"def auxiliar_{i}(x):\n"
        f'    """Auxiliar {i}."""\n'
        f"    resultado = Servico{i}().executar(x)\n    resultado += {i}\n    return resultado\n"
    )


def _montar(raiz: Path, jobs: int) -> None:
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "p"\nid = "p"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n\n'
        f"[index]\njobs = {jobs}\nmax_file_bytes = {MAX_FILE_BYTES}\n",
        encoding="utf-8",
    )
    for i in range(N_MODULOS):
        pasta = raiz / f"pkg{i % 4}"
        pasta.mkdir(exist_ok=True)
        (pasta / f"mod_{i}.py").write_text(_modulo(i), encoding="utf-8")
    (raiz / "docs").mkdir()
    for i in range(5):
        (raiz / "docs" / f"guia_{i}.md").write_text(
            f"# Guia {i}\n\n## Uso\n\nO Servico{i} faz o trabalho {i}.\n\n## Notas\n\nTexto longo o bastante.\n" * 3,
            encoding="utf-8",
        )
    (raiz / "dados.json").write_text('{"a": 1, "b": [1, 2, 3]}\n', encoding="utf-8")
    # um de cada destino do Gate:
    (raiz / "binario.py").write_bytes(b"x = 1\n\x00\x01\x02" * 50)  # binário
    (raiz / "grande.py").write_text("y = 1\n" * 10_000, encoding="utf-8")  # acima de max_file_bytes
    (raiz / ".env").write_text("SECRET_KEY=abc123\n", encoding="utf-8")  # bloqueado pelo nome
    (raiz / "vaza.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n\ndef usa():\n    return KEY\n', encoding="utf-8")
    (raiz / "estranho.xyz").write_text("nada a indexar\n", encoding="utf-8")  # extensão fora da lista
    (raiz / ".gitignore").write_text("ignorado/\n", encoding="utf-8")
    (raiz / "ignorado").mkdir()
    (raiz / "ignorado" / "x.py").write_text("z = 1\n", encoding="utf-8")


def _tabelas(cfg) -> dict[str, list[tuple]]:
    with open_db(cfg.db_path, read_only=True) as conn:
        def q(sql: str) -> list[tuple]:
            return sorted(tuple(r) for r in conn.execute(sql))

        return {
            "documents": q(
                "SELECT rel_path, id, lang, doc_kind, size_bytes, content_hash, redacted, title, chunker_version "
                "FROM documents WHERE rel_path != 'ragx.toml'"
            ),
            "chunks": q(
                "SELECT id, document_id, ordinal, parent_id, kind, symbol, heading_path, start_line, end_line, "
                "content, content_hash, token_count FROM chunks "
                "WHERE document_id NOT IN (SELECT id FROM documents WHERE rel_path = 'ragx.toml')"
            ),
            "security_events": q("SELECT path, rule_id, severity, action, line, digest, preview FROM security_events"),
            "fts": q(
                "SELECT f.content FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "
                "WHERE c.document_id NOT IN (SELECT id FROM documents WHERE rel_path = 'ragx.toml')"
            ),
            "file_verdicts": q("SELECT rel_path, verdict, rule_id, size_bytes FROM file_verdicts"),
        }


@pytest.fixture
def pool_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parallel, "PARALLEL_MIN_FILES", 1)


def test_jobs_4_e_jobs_1_dao_as_mesmas_tabelas(tmp_path: Path, pool_real: None) -> None:
    """Pool de processos real: `documents`, `chunks` (ids, conteúdo, ordinais), eventos, FTS e vereditos iguais."""
    seq, par = tmp_path / "seq", tmp_path / "par"
    seq.mkdir()
    _montar(seq, jobs=1)
    shutil.copytree(seq, par)
    (par / "ragx.toml").write_text(
        (seq / "ragx.toml").read_text(encoding="utf-8").replace("jobs = 1", "jobs = 4"), encoding="utf-8"
    )
    for raiz in (seq, par):  # as duas árvores partem do zero: sem `.ragx` copiado
        shutil.rmtree(raiz / ".ragx", ignore_errors=True)

    r_seq = index_project(load_config(seq))
    r_par = index_project(load_config(par))
    assert r_seq.parallel_jobs == 0
    assert r_par.parallel_jobs == 4 and r_par.parallel_fallback is None

    a, b = _tabelas(load_config(seq)), _tabelas(load_config(par))
    assert a["documents"] and a["chunks"] and a["security_events"] and a["file_verdicts"]
    for nome in a:
        assert a[nome] == b[nome], f"tabela {nome} difere entre jobs=1 e jobs=4"
    assert r_seq.stats.indexed == r_par.stats.indexed
    assert r_seq.stats.blocked == r_par.stats.blocked
    assert r_seq.stats.skipped == r_par.stats.skipped
    assert sorted(r_seq.blocked_paths) == sorted(r_par.blocked_paths)

    # cada destino do Gate deu o mesmo veredito, e o que tem de ficar de fora ficou
    rels = {r[0] for r in a["documents"]}
    assert "binario.py" not in rels and "grande.py" not in rels and ".env" not in rels
    assert "estranho.xyz" not in rels and "ignorado/x.py" not in rels
    assert "AKIAIOSFODNN7EXAMPLE" not in "".join(c[0] for c in b["fts"])


def test_abaixo_do_limiar_nao_cria_pool(tmp_path: Path) -> None:
    _montar(tmp_path, jobs=4)
    r = index_project(load_config(tmp_path))
    assert r.parallel_jobs == 0 and parallel.PARALLEL_MIN_FILES == 200
    assert not multiprocessing.active_children()


def test_jobs_1_nunca_cria_pool_mesmo_com_limiar_1(tmp_path: Path, pool_real: None) -> None:
    _montar(tmp_path, jobs=1)
    assert index_project(load_config(tmp_path)).parallel_jobs == 0


def test_dry_run_fica_sequencial(tmp_path: Path, pool_real: None) -> None:
    _montar(tmp_path, jobs=4)
    r = index_project(load_config(tmp_path), dry_run=True)
    assert r.parallel_jobs == 0 and not multiprocessing.active_children()


def test_resolve_jobs() -> None:
    assert resolve_jobs(1) == 1 and resolve_jobs(3) == 3
    assert 1 <= resolve_jobs(0) <= parallel.MAX_AUTO_JOBS
    assert resolve_jobs(-1) == resolve_jobs(0)


def test_reindexar_sem_mudanca_nao_cria_pool(tmp_path: Path, pool_real: None) -> None:
    _montar(tmp_path, jobs=2)
    cfg = load_config(tmp_path)
    assert index_project(cfg).parallel_jobs == 2
    r = index_project(cfg)  # nada a ler: todos `unchanged`
    assert r.parallel_jobs == 0 and r.stats.indexed == 0


def test_ctrl_c_no_meio_nao_deixa_processo_filho(tmp_path: Path, pool_real: None) -> None:
    _montar(tmp_path, jobs=2)
    cfg = load_config(tmp_path)
    vistos = {"n": 0}

    def interrompe(evento: dict) -> None:
        if evento.get("phase") == "scan":
            vistos["n"] += 1
            if vistos["n"] == 25:
                raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        index_project(cfg, on_event=interrompe)
    # o `finally` do gerador espera os lotes em voo e encerra o pool
    limite = time.monotonic() + 10
    while multiprocessing.active_children() and time.monotonic() < limite:
        time.sleep(0.05)
    assert not multiprocessing.active_children()
    with open_db(cfg.db_path, read_only=True) as conn:
        ultimo = conn.execute("SELECT error FROM index_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert ultimo["error"] == "interrupted"


# ── executor falso, em processo: erro, queda e ordem sem depender de `spawn` ───────────────
class _ExecutorFalso:
    """Roda o lote na hora, no processo do teste, e registra como foi desligado."""

    instancias: ClassVar[list[_ExecutorFalso]] = []
    falha_no_submit_numero: ClassVar[int | None] = None
    falha_no_resultado_numero: ClassVar[int | None] = None

    def __init__(self, max_workers: int, mp_context: object, initializer, initargs: tuple) -> None:
        self.max_workers = max_workers
        self.submits = 0
        self.desligado: dict | None = None
        initializer(*initargs)
        _ExecutorFalso.instancias.append(self)

    def submit(self, fn, *args) -> Future:
        self.submits += 1
        if self.falha_no_submit_numero == self.submits:
            raise BrokenProcessPool("submit")
        futuro: Future = Future()
        if self.falha_no_resultado_numero == self.submits:
            futuro.set_exception(BrokenProcessPool("resultado"))
            return futuro
        try:
            futuro.set_result(fn(*args))
        except BaseException as exc:
            futuro.set_exception(exc)
        return futuro

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        self.desligado = {"wait": wait, "cancel_futures": cancel_futures}


@pytest.fixture
def falso(monkeypatch: pytest.MonkeyPatch) -> type[_ExecutorFalso]:
    _ExecutorFalso.instancias = []
    _ExecutorFalso.falha_no_submit_numero = None
    _ExecutorFalso.falha_no_resultado_numero = None
    monkeypatch.setattr(parallel, "ProcessPoolExecutor", _ExecutorFalso)
    monkeypatch.setattr(parallel, "PARALLEL_MIN_FILES", 1)
    monkeypatch.setattr(parallel, "BATCH_FILES", 4)
    # `init_worker` roda no processo do teste: não pode deixar o Ctrl+C ignorado
    monkeypatch.setattr(signal, "signal", lambda *a, **k: None)
    return _ExecutorFalso


def test_erro_em_worker_propaga_com_o_caminho_e_desliga_o_pool(
    tmp_path: Path, falso: type[_ExecutorFalso], monkeypatch: pytest.MonkeyPatch
) -> None:
    _montar(tmp_path, jobs=2)
    original = parallel.prepare

    def quebra(rel_path, text, include_unknown, opts):
        if rel_path == "pkg2/mod_6.py":
            raise RuntimeError("falha forçada")
        return original(rel_path, text, include_unknown, opts)

    monkeypatch.setattr(parallel, "prepare", quebra)
    cfg = load_config(tmp_path)
    with pytest.raises(WorkerError, match=r"pkg2/mod_6\.py: RuntimeError: falha forçada"):
        index_project(cfg)
    assert falso.instancias and falso.instancias[-1].desligado == {"wait": True, "cancel_futures": True}
    with open_db(cfg.db_path, read_only=True) as conn:
        erro = conn.execute("SELECT error FROM index_runs ORDER BY id DESC LIMIT 1").fetchone()["error"]
    assert "pkg2/mod_6.py" in erro


def test_programa_sem_guarda_de_main_cai_para_o_sequencial_com_o_mesmo_resultado(
    tmp_path: Path, falso: type[_ExecutorFalso], monkeypatch: pytest.MonkeyPatch
) -> None:
    """O `spawn` levanta `RuntimeError` num script sem `if __name__ == "__main__"`: a indexação não pode quebrar por isso."""
    seq, par = tmp_path / "seq", tmp_path / "par"
    seq.mkdir()
    par.mkdir()
    _montar(seq, jobs=1)
    _montar(par, jobs=2)

    def recusa(self, fn, *args):  # type: ignore[no-untyped-def]
        raise RuntimeError("An attempt has been made to start a new process before the current process has finished its bootstrapping phase.")

    monkeypatch.setattr(_ExecutorFalso, "submit", recusa)
    r_par = index_project(load_config(par))
    index_project(load_config(seq))
    assert r_par.parallel_fallback is not None and "RuntimeError" in r_par.parallel_fallback
    a, b = _tabelas(load_config(seq)), _tabelas(load_config(par))
    for nome in a:
        assert a[nome] == b[nome], nome


@pytest.mark.parametrize("onde", ["submit", "resultado"])
def test_pool_que_cai_refaz_o_resto_no_principal_com_o_mesmo_resultado(
    tmp_path: Path, falso: type[_ExecutorFalso], onde: str
) -> None:
    seq, par = tmp_path / "seq", tmp_path / "par"
    seq.mkdir()
    par.mkdir()
    _montar(seq, jobs=1)
    _montar(par, jobs=2)
    setattr(falso, f"falha_no_{onde}_numero", 3)  # o 3º lote
    r_par = index_project(load_config(par))
    r_seq = index_project(load_config(seq))
    assert r_par.parallel_fallback is not None and "pool" in r_par.parallel_fallback
    assert r_seq.parallel_jobs == 0
    a, b = _tabelas(load_config(seq)), _tabelas(load_config(par))
    for nome in a:
        assert a[nome] == b[nome], nome


def test_a_ordem_da_varredura_e_preservada_e_os_lotes_sao_limitados(
    tmp_path: Path, falso: type[_ExecutorFalso]
) -> None:
    _montar(tmp_path, jobs=2)
    cfg = load_config(tmp_path)
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    itens = list(iter_candidates(cfg.root, gate, max_bytes=MAX_FILE_BYTES))
    esperado = [i.rel if isinstance(i, Candidate) else i.rel_path for i in itens]

    from ragx.indexing.pipeline import _worker_spec

    stats = ParallelStats()
    saida = [w.rel_path for w, _p in process_stream(itens, gate, _worker_spec(cfg), 2, stats)]
    # um candidato que o worker descarta (sumiu) simplesmente não aparece; aqui nenhum sumiu
    assert saida == esperado
    candidatos = sum(isinstance(i, Candidate) for i in itens)
    assert stats.jobs == 2 and stats.batches == -(-candidatos // 4)


def test_arquivo_que_sumiu_entre_a_varredura_e_a_leitura_nao_aparece(
    tmp_path: Path, falso: type[_ExecutorFalso]
) -> None:
    _montar(tmp_path, jobs=2)
    cfg = load_config(tmp_path)
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    itens = list(iter_candidates(cfg.root, gate, max_bytes=MAX_FILE_BYTES))
    (tmp_path / "pkg1" / "mod_5.py").unlink()

    from ragx.indexing.pipeline import _worker_spec

    saida = [w.rel_path for w, _p in process_stream(itens, gate, _worker_spec(cfg), 2)]
    assert "pkg1/mod_5.py" not in saida and "pkg0/mod_4.py" in saida
