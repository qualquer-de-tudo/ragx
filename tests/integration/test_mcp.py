"""Fase 6 — MCP como casca fina."""

from __future__ import annotations

import json

import pytest

from ragx.config import load_config
from ragx.dictionary import builder as dict_builder
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.mcp.operations import WriteAPI
from ragx.mcp.playbook import playbook
from ragx.mcp.server import KnowledgeAPI, RateLimiter, build_server
from ragx.mcp.tools import BuildContextRequest, SearchRequest, cap, validate_path

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios via SSO corporativo."""

    def login(self, credentials):
        """Valida o token e cria a sessao no Redis."""
        return self.sso.validate(credentials)
'''

DOC = "# Autenticacao\n\n## Fluxo SSO\n\nO AuthService valida o token no provedor.\n"


@pytest.fixture(scope="module")
def api(tmp_path_factory: pytest.TempPathFactory) -> KnowledgeAPI:
    root = tmp_path_factory.mktemp("mcp")
    (root / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "doc.md").write_text(DOC, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    data, _ = dict_builder.build(cfg)
    dict_builder.write(cfg, data)
    return KnowledgeAPI(cfg)


# ── envelope ────────────────────────────────────────────────────────────
def test_toda_resposta_tem_envelope(api: KnowledgeAPI) -> None:
    out = api.search(SearchRequest(query="autenticacao"), mode="hybrid")
    assert out["ok"] is True and "data" in out


def test_erro_nao_vaza_stack_trace(api: KnowledgeAPI) -> None:
    out = api.get_chunk("nao-existe")
    assert out["ok"] is False
    assert out["error"]["code"] == "not_found"
    assert "Traceback" not in json.dumps(out)


# ── atribuição obrigatória ──────────────────────────────────────────────
def test_todo_resultado_carrega_project(api: KnowledgeAPI) -> None:
    """Conhecimento sem origem identificada não é entregue."""
    out = api.search(SearchRequest(query="sessao"), mode="hybrid")
    assert out["data"]["results"]
    for hit in out["data"]["results"]:
        assert hit["project"] == "demo"


# ── a fronteira ─────────────────────────────────────────────────────────
def test_get_document_nao_le_do_disco(api: KnowledgeAPI) -> None:
    """Caminho não indexado é `not_found` — nunca uma tentativa de leitura."""
    out = api.get_document("auth.py")
    assert out["ok"] and out["data"]["document"]["path"] == "auth.py"

    inexistente = api.get_document("nao_indexado.py")
    assert not inexistente["ok"] and inexistente["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "ruim", ["/etc/passwd", "../../.env", "C:/Windows/System32", "a/../../b"]
)
def test_caminho_absoluto_ou_traversal_e_recusado(api: KnowledgeAPI, ruim: str) -> None:
    out = api.get_document(ruim)
    assert not out["ok"]
    assert out["error"]["code"] in ("invalid_path", "not_found")


@pytest.mark.parametrize("bom", ["src/a.py", "docs/auth.md", "a.py"])
def test_caminho_relativo_e_aceito(bom: str) -> None:
    assert validate_path(bom) == bom


@pytest.mark.parametrize("ruim", ["/abs", "../x", "C:/x", "a/../../b"])
def test_validate_path_recusa(ruim: str) -> None:
    assert validate_path(ruim) is None


def test_env_nunca_e_servido(api: KnowledgeAPI) -> None:
    for alvo in (".env", ".env.production", "credentials.json", "id_rsa"):
        out = api.get_document(alvo)
        assert not out["ok"], f"{alvo} foi servido"


# ── ferramentas ─────────────────────────────────────────────────────────
def test_get_dictionary(api: KnowledgeAPI) -> None:
    out = api.get_dictionary()
    assert out["ok"] and "technologies" in out["data"]["dictionary"]


def test_get_dictionary_por_secao(api: KnowledgeAPI) -> None:
    out = api.get_dictionary("services")
    assert out["ok"] and set(out["data"]["dictionary"]) == {"services"}


def test_secao_invalida_e_not_found(api: KnowledgeAPI) -> None:
    out = api.get_dictionary("inexistente")
    assert not out["ok"] and out["error"]["code"] == "not_found"


def test_get_chunk_devolve_conteudo(api: KnowledgeAPI) -> None:
    doc = api.get_document("auth.py")
    cid = doc["data"]["chunks"][0]["chunk_id"]
    out = api.get_chunk(cid)
    assert out["ok"] and out["data"]["content"] and out["data"]["project"] == "demo"


def test_get_entity(api: KnowledgeAPI) -> None:
    out = api.get_entity("AuthService")
    assert out["ok"] and out["data"]["entity"]["name"] == "AuthService"
    assert out["data"]["relations"]


def test_entidade_inexistente(api: KnowledgeAPI) -> None:
    assert api.get_entity("NaoExiste")["error"]["code"] == "not_found"


def test_search_graph(api: KnowledgeAPI) -> None:
    out = api.search_graph(SearchRequest(query="autenticacao"), depth=1)
    assert out["ok"] and "results" in out["data"]


def test_build_context_respeita_orcamento(api: KnowledgeAPI) -> None:
    out = api.build_context(BuildContextRequest(query="autenticacao", tokens=800))
    assert out["ok"]
    assert out["data"]["estimated_tokens"] <= 800
    assert out["data"]["markdown"]
    for f in out["data"]["fragments"]:
        assert f["document_path"] and f["lines"][0] > 0


def test_list_projects(api: KnowledgeAPI) -> None:
    out = api.list_projects()
    assert out["ok"] and out["data"]["projects"][0]["name"] == "demo"


# ── limites ─────────────────────────────────────────────────────────────
def test_limit_acima_do_teto_e_rejeitado() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SearchRequest(query="x", limit=500)


def test_tokens_acima_do_teto_e_rejeitado() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BuildContextRequest(query="x", tokens=999_999)


def test_scope_invalido_e_rejeitado() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SearchRequest(query="x", scope="tudo")
    SearchRequest(query="x", scope="all")
    SearchRequest(query="x", scope="project:outro")


def test_rate_limit_ativa_e_se_recupera() -> None:
    rl = RateLimiter(per_minute=3)
    assert [rl.allow() for _ in range(4)] == [True, True, True, False]
    rl._calls.clear()
    assert rl.allow()


def test_resposta_grande_e_recusada_nao_truncada() -> None:
    out = cap({"ok": True, "data": {"x": "a" * 5000}}, max_bytes=100)
    assert not out["ok"] and out["error"]["code"] == "too_large"
    assert "pagine" in out["error"]["message"]


_LEITURA = {
    "get_playbook", "get_dictionary", "search_knowledge", "search_hybrid",
    "get_document", "get_chunk", "get_entity", "search_graph", "build_context",
    "list_projects", "get_contract", "list_base_sources",
    # Fase 13 — orquestração (leitura)
    "analyze_request", "list_tasks", "get_task", "task_graph", "next_task",
    "task_status",
}
_ESCRITA = {
    "refresh", "reindex", "sync", "rebuild_graph", "generate_dictionary",
    "base_sync", "publish_contract",
    # Fase 13 — orquestração (escrita)
    "plan_work", "claim_task", "report_task_result", "release_task",
    "set_task_status", "add_task_dependency", "run_worker",
}


def test_servidor_registra_as_ferramentas(api: KnowledgeAPI) -> None:
    import asyncio

    nomes = {t.name for t in asyncio.run(build_server(api.cfg, allow_write=True).list_tools())}
    assert nomes == _LEITURA | _ESCRITA


def test_modo_leitura_ainda_expoe_as_ferramentas_de_escrita(api: KnowledgeAPI) -> None:
    """Esconder a ferramenta faria o agente concluir que a operação não existe.

    Ela aparece e responde `write_disabled`, dizendo como habilitar — a
    diferença entre "não posso" e "não sei que dá".
    """
    import asyncio

    nomes = {t.name for t in asyncio.run(build_server(api.cfg, allow_write=False).list_tools())}
    assert nomes >= _ESCRITA

    from ragx.mcp.orchestration import OrchestrationAPI

    ops = WriteAPI(api.cfg, enabled=False)
    orq = OrchestrationAPI(api.cfg, enabled=False)
    for chamada in (ops.reindex, ops.sync, ops.rebuild_graph, ops.refresh,
                    orq.run_worker, lambda: orq.claim_task(),
                    lambda: orq.release_task("x")):
        out = chamada()
        assert out["ok"] is False
        assert out["error"]["code"] == "write_disabled"
        assert "--write" in out["error"]["message"]


def test_escrita_habilitada_reindexa_de_verdade(api: KnowledgeAPI) -> None:
    ops = WriteAPI(api.cfg, enabled=True)
    out = ops.reindex()
    assert out["ok"] is True
    d = out["data"]
    assert d["operation"] == "reindex"
    assert d["files_seen"] > 0
    assert "duration_ms" in d
    # Caminho de arquivo bloqueado é um mapa de onde estão os segredos: sai
    # a contagem, nunca a lista.
    assert "blocked_paths" not in d


def test_playbook_ensina_a_ordem_e_os_limites(api: KnowledgeAPI) -> None:
    texto = playbook(api.cfg, write_enabled=True)["playbook"]
    for marca in ("get_dictionary", "search_hybrid", "build_context", "refresh"):
        assert marca in texto
    assert "não lê" in texto or "não abre o arquivo" in texto
    # Sem escrita o agente não pode ser instruído a reindexar.
    somente_leitura = playbook(api.cfg, write_enabled=False)["playbook"]
    assert "somente-leitura" in somente_leitura


def test_cli_e_mcp_concordam(api: KnowledgeAPI) -> None:
    """Mesmo serviço por baixo: divergência viraria bug relatado por agente."""
    from ragx.search.service import search

    cli = [r.chunk_id for r in search(api.cfg, "autenticacao", mode="hybrid", limit=5).results]
    mcp = [
        h["chunk_id"]
        for h in api.search(SearchRequest(query="autenticacao", limit=5), mode="hybrid")["data"][
            "results"
        ]
    ]
    assert cli == mcp


def test_erro_de_ferramenta_vira_resposta_estruturada(api: KnowledgeAPI) -> None:
    """Regressão: uma exceção dentro da ferramenta chegava ao agente como
    'Error executing tool X' — string sem código, sem causa, sem nada acionável.

    Encontrado conectando um cliente MCP real ao servidor.
    """
    from ragx.mcp.server import _guarded

    def explode() -> dict:
        raise ValueError("falha simulada")

    out = _guarded(explode, "ferramenta_teste", api.cfg)
    assert out["ok"] is False
    assert out["error"]["code"] == "internal"
    assert "ferramenta_teste" in out["error"]["message"]
    assert "ValueError" in out["error"]["message"]
    assert "falha simulada" not in out["error"]["message"], "detalhe vai só para o log"
    assert (api.cfg.state_dir / "logs" / "errors.log").is_file()


def test_dedup_nao_mistura_modelos_de_embedding(api: KnowledgeAPI) -> None:
    """Regressão: trocar de provider deixava vetores do modelo antigo no banco,
    e `dedupe_near` comparava 384 com 256 dimensões — ValueError no matmul."""
    import sqlite3

    from ragx.context.engine import _vectors_for

    conn = sqlite3.connect(api.cfg.db_path)
    conn.execute(
        "INSERT OR REPLACE INTO embedding_models"
        "(id, dim, versioned_dim, quant, normalized, created_at) "
        "VALUES ('modelo:antigo', 999, 999, 'int8', 1, '2000-01-01T00:00:00Z')"
    )
    cid = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT OR REPLACE INTO embeddings"
        "(chunk_id, model_id, vector, vector_q, q_scale, q_offset, created_at) "
        "VALUES (?, 'modelo:antigo', NULL, ?, 1.0, 0.0, 'x')",
        (cid, b"\x01" * 999),
    )
    conn.commit()
    conn.close()

    vectors, _q = _vectors_for(api.cfg, [cid], "consulta qualquer")
    dims = {v.shape[0] for v in vectors.values()}
    assert len(dims) <= 1, f"vetores de dimensões diferentes no mesmo conjunto: {dims}"


# ── toda operação de escrita é exercida de verdade ──────────────────────
_ESCRITA_SEM_ARGUMENTO = sorted(
    _ESCRITA - {"plan_work", "claim_task", "report_task_result", "release_task",
                "set_task_status", "add_task_dependency"}
)


@pytest.mark.parametrize("op", _ESCRITA_SEM_ARGUMENTO)
def test_toda_ferramenta_de_escrita_executa(api: KnowledgeAPI, op: str) -> None:
    """Cada uma é chamada, não só listada.

    Duas destas falharam em produção com `AttributeError` — `builder.build`
    devolve um relatório, não um dict, e `hub.push` simplesmente não existe.
    Os testes antigos verificavam que a ferramenta estava REGISTRADA e paravam
    aí; quem achou foi um cliente MCP real. Parametrizar sobre `_ESCRITA`
    garante que ferramenta nova nasça coberta.
    """
    from ragx.mcp.orchestration import OrchestrationAPI

    fachada = (
        WriteAPI(api.cfg, enabled=True)
        if hasattr(WriteAPI(api.cfg, enabled=True), op)
        else OrchestrationAPI(api.cfg, enabled=True)
    )
    out = getattr(fachada, op)()
    assert out["ok"] is True, out.get("error")
    if "operation" in out["data"]:  # as de índice carregam operação e duração
        assert out["data"]["operation"] == op
        assert out["data"]["duration_ms"] >= 0


def test_pasta_sem_indice_nao_vira_erro_interno(tmp_path, monkeypatch) -> None:
    """O servidor global sobe em TODA sessão, inclusive fora de um projeto.

    "Ainda não há índice aqui" é o estado normal dessas pastas. Responder
    `internal` e mandar olhar `.ragx/logs/errors.log` — que não existe — faz o
    agente concluir que o RAGX está quebrado e parar de consultá-lo.
    """
    from ragx.config import load_config
    from ragx.mcp.server import _guarded

    vazio = tmp_path / "sem-projeto"
    vazio.mkdir()
    monkeypatch.chdir(vazio)
    cfg = load_config(vazio)
    assert not cfg.db_path.exists()

    def explode():
        from ragx.core.errors import EnvError

        raise EnvError("banco não encontrado")

    out = _guarded(explode, "search_hybrid", cfg)
    assert out["ok"] is False
    assert out["error"]["code"] == "not_indexed"
    # A mensagem precisa dizer o que fazer, e não apontar para um log ausente.
    assert "ragx init" in out["error"]["message"]
    assert "errors.log" not in out["error"]["message"]
