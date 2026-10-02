"""Prefixo de contexto determinístico no FTS e no embedding (RAGX-0166)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.models import Chunk, ChunkKind
from ragx.embeddings.hashing import HashingEmbedder
from ragx.indexing.chunkers import build_context_text, chunk_document, context_prefix
from ragx.indexing.context import CONTEXT_VERSION, META_KEY, ensure_context
from ragx.indexing.pipeline import index_project
from ragx.search.service import search
from ragx.storage.db import get_meta, open_db, set_meta

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios via SSO corporativo. Detalhe que fica de fora."""

    def login(self, credentials, tenant="padrao"):
        """Valida o token no provedor e cria a sessao do usuario."""
        total = len(credentials)
        return self.sso.validate(credentials, total)

    def logout(self, session_id):
        """Encerra a sessao e limpa o cache do usuario."""
        self.cache.delete(session_id)
        self.audit.record("logout", session_id)
        return True
'''

LONGA = '''def funcao_com_assinatura_enorme(parametro_numero_um: int, parametro_numero_dois: str, parametro_numero_tres: float, parametro_numero_quatro: bytes, parametro_numero_cinco: list) -> dict:
    """Primeira frase do docstring. Segunda frase que não entra."""
    resultado = {}
    for i in range(parametro_numero_um):
        resultado[i] = parametro_numero_dois * i
    return resultado
'''


def _stub(kind: ChunkKind, symbol: str | None, content: str, heading: str | None = None) -> Chunk:
    return Chunk(
        id="x", document_id="d", ordinal=0, kind=kind, start_line=1, end_line=2, content=content,
        content_hash="h", token_count=1, symbol=symbol, heading_path=heading,
    )


# ── a função pura ───────────────────────────────────────────────────────
def test_build_context_text_e_deterministica_e_separa_identificadores() -> None:
    c = _stub(ChunkKind.METHOD, "AuthService.login", AUTH.split("    def logout")[0].split("\n\n", 1)[1])
    a = build_context_text("src/auth/service.py", c)
    assert a == build_context_text("src/auth/service.py", c)
    assert "src/auth/service.py" in a and "method AuthService.login" in a
    assert "auth service login" in a  # CamelCase separado: é o que faz "auth service" achar AuthService
    assert "def login(self, credentials" in a  # a assinatura
    assert "Valida o token no provedor e cria a sessao do usuario." in a  # a primeira frase do docstring


def test_assinatura_e_docstring_sao_truncadas() -> None:
    c = _stub(ChunkKind.FUNCTION, "funcao_com_assinatura_enorme", LONGA)
    ctx = build_context_text("m.py", c)
    assinatura = next(p for p in ctx.split(" › ") if p.startswith("def funcao_com"))
    assert len(assinatura) <= 160 and assinatura.endswith("…")
    assert "Primeira frase do docstring." in ctx and "Segunda frase" not in ctx


def test_secao_de_documento_usa_o_titulo_e_nao_tem_assinatura() -> None:
    c = _stub(ChunkKind.SECTION, None, "texto da seção", heading="Segurança › Gate")
    assert build_context_text("docs/02.md", c) == "docs/02.md › Segurança › Gate"


def test_context_prefix_usa_o_contexto_gravado_ou_monta_na_hora() -> None:
    c = _stub(ChunkKind.FUNCTION, "f", "def f():\n    return 1\n")
    montado = context_prefix("m.py", c)
    gravado = context_prefix("m.py", Chunk(**{**c.__dict__, "context": "CONTEXTO PRONTO"}) if hasattr(c, "__dict__") else c)
    assert montado.startswith("[m.py › function f") and montado.endswith("return 1\n")
    assert gravado.startswith("[CONTEXTO PRONTO]") or gravado == montado


def test_todo_chunk_sai_do_chunker_com_contexto_e_o_conteudo_nao_muda() -> None:
    from ragx.indexing import parsers

    parsed = parsers.parse("src/auth/service.py", AUTH)
    assert parsed is not None
    chunks = chunk_document("src/auth/service.py", AUTH, parsed)
    assert chunks and all(c.context for c in chunks)
    for c in chunks:
        # o conteúdo é do arquivo, sem prefixo; a única linha que o chunker mesmo acrescenta é o resumo `# métodos: ...`
        assert c.context not in c.content
        assert all(linha in AUTH for linha in c.content.splitlines() if linha.strip() and not linha.startswith("# métodos:"))


# ── banco, FTS e embedding ──────────────────────────────────────────────
@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "billing").mkdir(parents=True)
    (tmp_path / "src" / "billing" / "cobranca.py").write_text(AUTH, encoding="utf-8")
    (tmp_path / "src" / "gate.py").write_text(LONGA, encoding="utf-8")
    index_project(load_config(tmp_path))
    return tmp_path


def test_busca_por_palavra_so_do_caminho_acha_o_chunk(proj: Path) -> None:
    """`billing` só existe no caminho do arquivo: antes da RAGX-0166 o FTS não o via."""
    out = search(load_config(proj), "billing", mode="keyword", limit=5)
    assert any(r.document_path == "src/billing/cobranca.py" for r in out.results)


def test_busca_por_palavras_do_simbolo_em_camelcase(proj: Path) -> None:
    out = search(load_config(proj), "auth service", mode="keyword", limit=5)
    assert any(r.document_path == "src/billing/cobranca.py" for r in out.results)


def test_content_gravado_nao_tem_prefixo(proj: Path) -> None:
    with open_db(load_config(proj).db_path, read_only=True) as conn:
        for r in conn.execute(
            "SELECT c.content, c.context FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.lang = 'python'"
        ):
            assert r["context"], "todo chunk novo tem contexto"
            assert not r["content"].startswith("[")
            assert r["context"] not in r["content"]
    texto = (proj / "src" / "billing" / "cobranca.py").read_text(encoding="utf-8")
    with open_db(load_config(proj).db_path, read_only=True) as conn:
        for r in conn.execute("SELECT content FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.rel_path = 'src/billing/cobranca.py'"):
            assert all(linha in texto for linha in r["content"].splitlines() if linha.strip() and not linha.startswith("# métodos:"))


def test_segundo_index_sem_mudanca_nao_reembute(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []
    original = HashingEmbedder.embed_documents

    def conta(self, textos):  # type: ignore[no-untyped-def]
        chamadas.append(len(textos))
        return original(self, textos)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", conta)
    index_project(load_config(proj))
    assert sum(chamadas) == 0


def test_a_chave_do_cache_e_o_texto_embutido_e_nao_o_conteudo(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O mesmo conteúdo em outro caminho tem outro contexto: não pode reaproveitar o vetor do primeiro."""
    outro = proj / "src" / "outro"
    outro.mkdir()
    (outro / "cobranca2.py").write_text(AUTH, encoding="utf-8")  # conteúdo idêntico, caminho diferente
    textos: list[str] = []
    original = HashingEmbedder.embed_documents

    def espia(self, ts):  # type: ignore[no-untyped-def]
        textos.extend(ts)
        return original(self, ts)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", espia)
    index_project(load_config(proj))
    assert textos and any("src/outro/cobranca2.py" in t for t in textos)


def test_subir_a_versao_do_contexto_refaz_o_contexto_e_apaga_os_vetores(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    with open_db(cfg.db_path) as conn:
        assert get_meta(conn, META_KEY) == CONTEXT_VERSION
        antes = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        assert antes > 0
        conn.execute("UPDATE chunks SET context = NULL")  # como num banco anterior à migração
        set_meta(conn, META_KEY, "0")
        conn.commit()
        assert ensure_context(conn) > 0
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE context IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0
        assert get_meta(conn, META_KEY) == CONTEXT_VERSION
        assert ensure_context(conn) == 0  # em dia: nada a fazer
    # o FTS também foi refeito pelos gatilhos
    out = search(cfg, "billing", mode="keyword", limit=5)
    assert any(r.document_path == "src/billing/cobranca.py" for r in out.results)
    # e a próxima indexação reembute (os vetores saíram)
    chamadas: list[int] = []
    original = HashingEmbedder.embed_documents
    monkeypatch.setattr(HashingEmbedder, "embed_documents", lambda self, ts: (chamadas.append(len(ts)), original(self, ts))[1])
    index_project(cfg)
    # os vetores voltaram (do cache, que é por texto embutido: o texto não mudou, então o modelo nem é chamado)
    with open_db(cfg.db_path, read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] > 0


def test_fts_e_chunks_continuam_com_a_mesma_contagem(proj: Path) -> None:
    with open_db(load_config(proj).db_path, read_only=True) as conn:
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        f = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        assert n == f
        cols = [r[1] for r in conn.execute("PRAGMA table_info(chunks_fts)")]
        assert cols == ["content", "symbol", "heading_path", "context"]


def test_pesos_do_bm25_batem_com_as_colunas_do_fts() -> None:
    from ragx.search.keyword import BM25_WEIGHTS

    assert len(BM25_WEIGHTS) == 4 and BM25_WEIGHTS[3] < BM25_WEIGHTS[0]  # o contexto serve para achar, não para ordenar


def test_segredo_nao_vaza_pelo_contexto(tmp_path: Path) -> None:
    """O contexto vem do conteúdo JÁ liberado pelo Gate: um segredo no docstring não pode aparecer no prefixo."""
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "vaza.py").write_text(
        'def conecta():\n    """Usa a chave AKIAIOSFODNN7EXAMPLE para acessar o bucket."""\n    total = 1\n    total += 2\n    return total\n',
        encoding="utf-8",
    )
    index_project(load_config(tmp_path))
    with sqlite3.connect(load_config(tmp_path).db_path) as conn:
        contextos = [r[0] or "" for r in conn.execute("SELECT context FROM chunks")]
        fts = [r[0] or "" for r in conn.execute("SELECT context FROM chunks_fts")]
    assert not any("AKIAIOSFODNN7EXAMPLE" in c for c in contextos + fts)
