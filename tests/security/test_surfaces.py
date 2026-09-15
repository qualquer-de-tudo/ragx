"""As superfícies de vazamento, testadas sobre o índice real.

Cada superfície ainda inexistente fica xfail; virar cada xfail em pass é DoD da
fase correspondente (ver task/README.md).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.secrets_under_test import (
    FIXTURE_ROOT,
    MUST_BLOCK,
    MUST_INDEX,
    SECRETS_UNDER_TEST,
    leaked,
)
from ragx.config import load_config
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def indexado(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Indexa a fixture de segredos de ponta a ponta, uma vez."""
    root = tmp_path_factory.mktemp("surf") / "proj"
    shutil.copytree(FIXTURE_ROOT, root)
    (root / "ragx.toml").write_text(
        '[project]\nname = "fixture"\nid = "test"\n\n'
        '[security]\npolicy = "strict"\n\n'
        # provider determinístico: a superfície de embeddings precisa de vetores
        # reais, mas não de rede nem de daemon
        '[embedding]\nprovider = "hashing"\ndim = 256\nversioned_dim = 128\n',
        encoding="utf-8",
    )
    cfg = load_config(root)
    index_project(cfg)
    return cfg.db_path


def _dump_all(db: Path) -> str:
    """Todo o conteúdo textual do banco, inclusive o índice FTS."""
    conn = sqlite3.connect(db)
    parts: list[str] = []
    tables = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if not r[0].startswith("sqlite_")
    ]
    for t in tables:
        try:
            for row in conn.execute(f'SELECT * FROM "{t}"'):
                parts.append(" ".join(str(v) for v in row))
        except sqlite3.OperationalError:
            continue  # tabelas internas do FTS5 não são selecionáveis assim
    conn.close()
    return "\n".join(parts)


# ── Superfície: database ────────────────────────────────────────────────
def test_superficie_database(indexado: Path) -> None:
    """Fase 1 — RAGX-0021. Nenhum segredo em nenhuma tabela, FTS incluído."""
    vazou = leaked(_dump_all(indexado))
    assert vazou == [], f"segredos no banco: {vazou}"


def test_arquivos_bloqueados_nao_viraram_documento(indexado: Path) -> None:
    conn = sqlite3.connect(indexado)
    paths = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    conn.close()
    for rel in MUST_BLOCK:
        assert rel not in paths, f"{rel} foi indexado apesar de bloqueado"


def test_arquivos_legitimos_foram_indexados(indexado: Path) -> None:
    """Sem isto, um gate que bloqueia tudo passaria em todas as varreduras."""
    conn = sqlite3.connect(indexado)
    paths = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    for rel in MUST_INDEX:
        if rel.endswith((".py", ".md")):
            assert rel in paths, f"{rel} deveria ter sido indexado; indexados: {sorted(paths)}"
    assert chunks > 0


def test_security_events_registram_sem_revelar(indexado: Path) -> None:
    conn = sqlite3.connect(indexado)
    rows = list(conn.execute("SELECT path, rule_id, severity, digest, preview FROM security_events"))
    conn.close()
    assert rows, "os bloqueios precisam deixar rastro auditável"
    assert leaked(" ".join(str(v) for r in rows for v in r)) == []


def test_busca_fts_por_segredo_nao_devolve_nada(indexado: Path) -> None:
    """Consulta direta no índice de texto — o caminho mais óbvio de vazamento."""
    conn = sqlite3.connect(indexado)
    for termo in ("AKIAIOSFODNN7EXAMPLE", "POSTGRES_PASSWORD", "BEGIN RSA PRIVATE KEY"):
        safe = termo.replace('"', "")
        rows = conn.execute(
            'SELECT content FROM chunks_fts WHERE chunks_fts MATCH ?', (f'"{safe}"',)
        ).fetchall()
        assert leaked(" ".join(str(r[0]) for r in rows)) == []
    conn.close()


# ── Superfícies das fases seguintes ─────────────────────────────────────
def test_superficie_embeddings(indexado: Path) -> None:
    """Fase 2 — RAGX-0027. Nenhum vetor pode derivar de arquivo bloqueado."""
    conn = sqlite3.connect(indexado)
    rows = conn.execute(
        """SELECT d.rel_path, c.content FROM embeddings e
           JOIN chunks c ON c.id = e.chunk_id
           JOIN documents d ON d.id = c.document_id"""
    ).fetchall()
    n_emb = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()

    assert n_emb > 0, "sem embeddings a varredura passaria por vacuidade"
    assert n_emb == n_chunks, "todo chunk admitido precisa ter vetor"
    paths = {r[0] for r in rows}
    for rel in MUST_BLOCK:
        assert rel not in paths, f"{rel} gerou embedding apesar de bloqueado"
    assert leaked(" ".join(r[1] for r in rows)) == []


def test_busca_por_segredo_nao_devolve_nada(indexado: Path) -> None:
    """O caminho que um agente realmente usaria para extrair um segredo."""
    from ragx.config import load_config
    from ragx.search.service import search

    cfg = load_config(indexado.parent.parent)
    for secret in SECRETS_UNDER_TEST:
        for mode in ("keyword", "semantic", "hybrid"):
            out = search(cfg, secret[:40], mode=mode, limit=10)
            corpo = " ".join(r.content for r in out.results)
            assert leaked(corpo) == [], f"{mode} vazou ao buscar por {secret[:12]}…"


def test_superficie_graph(indexado: Path) -> None:
    """Fase 3 — RAGX-0034. Nenhuma entidade ou relação pode derivar de arquivo
    bloqueado, e nenhum nome de entidade pode conter um segredo."""
    from ragx.config import load_config
    from ragx.graph.service import rebuild

    cfg = load_config(indexado.parent.parent)
    rebuild(cfg)

    conn = sqlite3.connect(indexado)
    entidades = conn.execute(
        "SELECT type, name, qualified_name, COALESCE(summary, '') FROM entities"
    ).fetchall()
    origens = {
        r[0]
        for r in conn.execute(
            """SELECT d.rel_path FROM entities e
               JOIN documents d ON d.id = e.document_id"""
        )
    }
    n = len(entidades)
    conn.close()

    assert n > 0, "sem grafo a varredura passaria por vacuidade"
    assert leaked(" ".join(str(v) for row in entidades for v in row)) == []
    for rel in MUST_BLOCK:
        assert rel not in origens, f"{rel} gerou entidade apesar de bloqueado"


def test_graph_search_nao_devolve_segredo(indexado: Path) -> None:
    from ragx.config import load_config
    from ragx.graph.service import graph_search

    cfg = load_config(indexado.parent.parent)
    for secret in SECRETS_UNDER_TEST[:4]:
        out = graph_search(cfg, secret[:40], limit=10)
        assert leaked(" ".join(r.content for r in out.results)) == []


def test_superficie_mcp(indexado: Path) -> None:
    """Fase 6 — RAGX-0049. Para CADA segredo, TODAS as ferramentas são chamadas
    com o segredo como query e com o caminho do arquivo bloqueado."""
    from ragx.config import load_config
    from ragx.mcp.server import KnowledgeAPI
    from ragx.mcp.tools import BuildContextRequest, SearchRequest

    cfg = load_config(indexado.parent.parent)
    cfg.mcp.rate_per_min = 100_000  # o teste faz centenas de chamadas de propósito
    api = KnowledgeAPI(cfg)

    for secret in SECRETS_UNDER_TEST:
        probe = secret[:40]
        respostas = [
            api.get_dictionary(),
            api.search(SearchRequest(query=probe), mode="semantic"),
            api.search(SearchRequest(query=probe), mode="hybrid"),
            api.get_document(probe),
            api.get_chunk(probe),
            api.get_entity(probe),
            api.search_graph(SearchRequest(query=probe), depth=1),
            api.build_context(BuildContextRequest(query=probe, tokens=1000)),
            api.list_projects(),
        ]
        for r in respostas:
            assert leaked(json.dumps(r, ensure_ascii=False, default=str)) == [], (
                f"ferramenta MCP vazou ao receber {secret[:12]}…"
            )


def test_mcp_recusa_servir_arquivo_bloqueado(indexado: Path) -> None:
    from ragx.config import load_config
    from ragx.mcp.server import KnowledgeAPI

    api = KnowledgeAPI(load_config(indexado.parent.parent))
    for rel in MUST_BLOCK:
        out = api.get_document(rel)
        assert not out["ok"], f"{rel} foi servido pelo MCP"
        assert out["error"]["code"] in ("not_found", "invalid_path")


def test_superficie_export(indexado: Path, tmp_path: Path) -> None:
    """Fase 8 — RAGX-0056. O pacote descompactado não pode conter segredo."""
    import zipfile

    from ragx.config import load_config
    from ragx.portability import package

    cfg = load_config(indexado.parent.parent)
    alvo = tmp_path / "surface.rag"
    package.export(cfg, alvo)

    with zipfile.ZipFile(alvo) as z:
        nomes = z.namelist()
        corpo = b"".join(z.read(n) for n in nomes).decode("utf-8", "replace")
    assert len(nomes) > 3, "pacote vazio passaria por vacuidade"
    assert leaked(corpo) == [], "segredo no pacote exportado"

    for marca in ("C:/Users", "C:\\Users", "/home/", "AppData"):
        assert marca not in corpo, f"caminho absoluto no pacote: {marca}"


def test_export_recusa_quando_ha_segredo_no_indice(indexado: Path, tmp_path: Path) -> None:
    """Defesa em profundidade: mesmo que algo escape do gate, o export barra."""
    from ragx.config import load_config
    from ragx.core.errors import SecurityBlockedError
    from ragx.portability import package
    from ragx.storage.db import open_db

    cfg = load_config(indexado.parent.parent)
    with open_db(cfg.db_path) as conn:
        conn.execute(
            "UPDATE chunks SET content = ? WHERE id = (SELECT id FROM chunks LIMIT 1)",
            (f'KEY = "{SECRETS_UNDER_TEST[0]}"',),
        )
        conn.commit()
    alvo = tmp_path / "bloqueado.rag"
    try:
        with pytest.raises(SecurityBlockedError):
            package.export(cfg, alvo)
        assert not alvo.exists(), "nada pode ser gravado quando há achado crítico"
    finally:
        # restaura o índice para os demais testes do módulo
        from ragx.indexing.pipeline import index_project

        index_project(cfg, full=True)


def test_superficie_knowledge(indexado: Path) -> None:
    """Fase 9 — RAGX-0059. `knowledge/` vai para o Git: é superfície de
    vazamento de primeira classe."""
    from ragx.config import load_config
    from ragx.sync import serialize

    cfg = load_config(indexado.parent.parent)
    serialize.serialize(cfg)
    kdir = cfg.root / "knowledge"
    assert kdir.is_dir()

    arquivos = [p for p in kdir.rglob("*") if p.is_file()]
    assert len(arquivos) > 3, "knowledge/ vazio passaria por vacuidade"

    corpo = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in arquivos
        if p.suffix in (".json", ".jsonl")
    )
    assert leaked(corpo) == [], "segredo em knowledge/"

    # E os arquivos bloqueados não podem ter virado artefato.
    nomes = {p.name for p in arquivos}
    for rel in MUST_BLOCK:
        assert f"{serialize.artifact_name(rel)}.json" not in nomes, f"{rel} versionado"


def test_superficie_federation(indexado: Path) -> None:
    """Fase 11 — RAGX-0073. A fatia é artefato COMPARTILHADO: vai para o Git e
    pode ser entregue a quem não tem acesso ao repositório."""
    from ragx.config import load_config
    from ragx.federation import slice as fed_slice

    cfg = load_config(indexado.parent.parent)
    r = fed_slice.build(cfg)
    folder = cfg.root / "knowledge" / fed_slice.FOLDER
    assert folder.is_dir()

    corpo = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in folder.rglob("*") if p.is_file()
    )
    assert leaked(corpo) == [], "segredo na fatia de federação"
    assert r.provides + r.consumes >= 0

    for marca in ("C:/Users", "AppData", "/home/"):
        assert marca not in corpo, f"caminho absoluto na fatia: {marca}"


def test_superficie_hub(indexado: Path, tmp_path: Path, monkeypatch) -> None:
    """Fase 11 — RAGX-0078. Dois projetos no hub, um deles com a fixture de
    segredos: nenhuma consulta a partir do outro pode retornar nada dela."""
    from ragx.config import load_config
    from ragx.federation import hub as hub_mod
    from ragx.federation import slice as fed_slice
    from ragx.federation.search import search_scoped
    from ragx.indexing.pipeline import index_project

    monkeypatch.setenv("RAGX_HUB_PATH", str(tmp_path / "hub"))

    contaminado = indexado.parent.parent  # projeto com a fixture de segredos
    fed_slice.build(load_config(contaminado))

    limpo = tmp_path / "limpo"
    limpo.mkdir()
    (limpo / "ragx.toml").write_text(
        '[project]\nname = "limpo"\nid = "limpo"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (limpo / "app.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    cfg_limpo = load_config(limpo)
    index_project(cfg_limpo)

    hub_mod.register(cfg_limpo, limpo)
    hub_mod.register(cfg_limpo, contaminado, name="contaminado")
    hub_mod.sync(cfg_limpo)

    # consultas a partir do projeto LIMPO, buscando pelos segredos do outro
    for secret in SECRETS_UNDER_TEST:
        for scope in ("all", "project:contaminado"):
            out = search_scoped(cfg_limpo, secret[:40], scope=scope, limit=10)
            corpo = json.dumps(
                [{"p": r.project, "c": r.content, "s": r.symbol} for r in out.results],
                ensure_ascii=False,
            )
            assert leaked(corpo) == [], f"hub vazou em scope={scope}"

    # e o hub inteiro não pode conter segredo
    conn = hub_mod.open_hub(cfg_limpo, read_only=True)
    blob = " ".join(
        str(v) for row in conn.execute("SELECT * FROM federation_items") for v in row
    )
    conn.close()
    assert leaked(blob) == [], "segredo materializado no hub"
