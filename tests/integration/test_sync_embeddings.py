"""Clone novo usa os embeddings versionados de `knowledge/` (RAGX-0144)."""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.embeddings.hashing import HashingEmbedder
from ragx.indexing.embed import embed_pending
from ragx.indexing.pipeline import index_project
from ragx.search.service import search
from ragx.storage.db import open_db
from ragx.sync import embeddings_import, serialize
from ragx.sync.service import sync

pytestmark = pytest.mark.integration

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


def _projeto(raiz: Path) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    # vocabulário distinto por módulo: com textos quase iguais há empate exato de similaridade, e a
    # ordem do empate depende da ordem de inserção (que o import de `knowledge/` não preserva)
    temas = ["pagamento fatura", "estoque armazem", "frete entrega", "cadastro cliente", "relatorio mensal", "notificacao email"]
    for i, tema in enumerate(temas):
        codigo = "\n".join([
            f"class Servico{i}:",
            f'    """Autentica usuarios do dominio {tema} no modulo {i}."""',
            "",
            "    def rodar(self, x):",
            f"        # {tema} {tema[::-1]}",
            f"        return x + {i}",
            "",
        ])
        (raiz / f"m{i}.py").write_text(codigo, encoding="utf-8")
    (raiz / "guia.md").write_text("# Guia\n\n## Login\n\nO usuario entra pelo SSO corporativo.\n", encoding="utf-8")
    return raiz


@pytest.fixture()
def origem(tmp_path: Path) -> Path:
    """Um projeto indexado cujo `sync` já gravou `knowledge/` (o que um colega comitaria)."""
    raiz = _projeto(tmp_path / "origem")
    sync(load_config(raiz))
    return raiz


def _clonar(origem: Path, destino: Path) -> Path:
    shutil.copytree(origem, destino, ignore=shutil.ignore_patterns(".ragx"))
    return destino


@pytest.fixture()
def textos(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Todo texto que chega ao embedder de documentos."""
    enviados: list[str] = []
    original = HashingEmbedder.embed_documents

    def espia(self, textos):  # type: ignore[no-untyped-def]
        enviados.extend(textos)
        return original(self, textos)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", espia)
    return enviados


def _linhas(cfg) -> dict[str, int]:  # type: ignore[no-untyped-def]
    with open_db(cfg.db_path, read_only=True) as c:
        return {
            "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "embeddings": c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0],
            "grosseiros": c.execute("SELECT COUNT(*) FROM embeddings WHERE vector IS NULL").fetchone()[0],
        }


# ── o fluxo de um clone novo ────────────────────────────────────────────
def test_sync_em_clone_sem_banco_funciona_e_nao_reembute_nada(origem: Path, tmp_path: Path, textos: list[str]) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    cfg = load_config(clone)
    assert not cfg.db_path.exists()
    textos.clear()

    rel = sync(cfg)

    assert textos == []  # nenhum texto foi ao embedder
    n = _linhas(cfg)
    assert n["chunks"] > 0 and n["embeddings"] == n["chunks"] == n["grosseiros"]
    assert rel.imported_embeddings == n["chunks"] and rel.coarse_only == n["chunks"]
    assert rel.embedded == 0
    # e a busca seguinte devolve resultados
    assert search(cfg, "autentica usuarios", mode="hybrid").results


def test_arquivo_editado_depois_do_clone_embute_so_os_chunks_dele(origem: Path, tmp_path: Path, textos: list[str]) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    (clone / "m2.py").write_text(
        "class Servico2:\n    \"\"\"Texto novo e bem diferente.\"\"\"\n\n    def rodar(self, x):\n        return x * 99\n",
        encoding="utf-8",
    )
    cfg = load_config(clone)
    textos.clear()
    rel = sync(cfg)
    assert 0 < len(textos) <= 3  # só os chunks do m2.py
    assert all("Servico2" in t or "Texto novo" in t or "m2.py" in t for t in textos)
    n = _linhas(cfg)
    assert n["embeddings"] == n["chunks"]
    assert n["grosseiros"] == n["chunks"] - rel.embedded  # os novos têm float32; os importados ficam grosseiros


def test_modelo_diferente_nao_importa_nada_e_avisa(origem: Path, tmp_path: Path, textos: list[str]) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    (clone / "ragx.toml").write_text(TOML.replace("dim = 64", "dim = 128").replace("versioned_dim = 32", "versioned_dim = 64"), encoding="utf-8")
    cfg = load_config(clone)
    rel = sync(cfg)
    assert rel.imported_embeddings == 0
    assert any("nada foi importado" in w for w in rel.warnings), rel.warnings
    assert len(textos) > 0  # sem import, o sync embute tudo
    assert _linhas(cfg)["grosseiros"] == 0


def test_o_import_nunca_sobrescreve_vetor_completo(origem: Path, tmp_path: Path) -> None:
    cfg = load_config(origem)  # já tem float32 para todos
    with open_db(cfg.db_path) as conn:
        antes = {r[0]: bytes(r[1]) for r in conn.execute("SELECT chunk_id, vector FROM embeddings")}
        rel = embeddings_import.import_embeddings(cfg, conn)
        depois = {r[0]: bytes(r[1]) for r in conn.execute("SELECT chunk_id, vector FROM embeddings")}
    assert rel.imported == 0 and antes == depois


# ── shards que não merecem confiança ────────────────────────────────────
def _shards(clone: Path) -> list[Path]:
    return sorted((clone / "knowledge" / "embeddings").glob("shard-*.i8"))


def test_shard_com_magic_errado_ou_tamanho_incoerente_e_ignorado_e_contado(origem: Path, tmp_path: Path) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    com_dados = [p for p in _shards(clone) if len(p.read_bytes()) > 20]
    assert len(com_dados) >= 2
    com_dados[0].write_bytes(b"LIXO" + com_dados[0].read_bytes()[4:])  # magic errado
    truncado = com_dados[1].read_bytes()
    com_dados[1].write_bytes(truncado[:-5])  # tamanho incoerente com a contagem declarada
    cfg = load_config(clone)
    index_project(cfg, embed=False)
    with open_db(cfg.db_path) as conn:
        rel = embeddings_import.import_embeddings(cfg, conn)
    assert rel.skipped_bad >= 2
    assert rel.imported > 0  # os shards bons entram
    assert _linhas(cfg)["embeddings"] <= _linhas(cfg)["chunks"]


def test_vetor_de_tamanho_errado_ou_escala_nao_finita_e_recusado(origem: Path, tmp_path: Path) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    cfg = load_config(clone)
    index_project(cfg, embed=False)
    alvo = next(p for p in _shards(clone) if len(p.read_bytes()) > 40)
    blob = bytearray(alvo.read_bytes())
    inicio = len(serialize._SHARD_MAGIC) + 8
    struct.pack_into("<ff", blob, inicio + 16, float("nan"), 0.0)  # escala NaN na 1ª entrada
    alvo.write_bytes(bytes(blob))
    with open_db(cfg.db_path) as conn:
        rel = embeddings_import.import_embeddings(cfg, conn)
    assert rel.skipped_bad == 1


# ── a busca avisa e depois fica igual a um índice do zero ────────────────
def test_busca_com_vetor_grosseiro_avisa_e_o_upgrade_deixa_igual_ao_do_zero(origem: Path, tmp_path: Path) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    cfg = load_config(clone)
    sync(cfg)
    r = search(cfg, "autentica usuarios no modulo", mode="hybrid")
    assert r.results and r.degraded is None
    assert r.partial and "grosseiros" in r.partial

    with open_db(cfg.db_path) as conn:
        rel = embed_pending(cfg, conn, upgrade_coarse=True)
        conn.commit()
    assert rel.coarse_only == 0
    r2 = search(cfg, "autentica usuarios no modulo", mode="hybrid")
    assert r2.partial is None

    # o mesmo corpus (inclusive o que há em `knowledge/`), mas SEM os vetores versionados: do zero
    do_zero = _clonar(origem, tmp_path / "zero")
    shutil.rmtree(do_zero / "knowledge" / "embeddings")
    zcfg = load_config(do_zero)
    index_project(zcfg)
    assert _linhas(zcfg)["grosseiros"] == 0
    consultas = ["autentica usuarios no modulo", "login SSO corporativo", "Servico3 rodar"]
    for q in consultas:
        a = [x.chunk_id for x in search(cfg, q, mode="hybrid").results]
        b = [x.chunk_id for x in search(zcfg, q, mode="hybrid").results]
        assert a == b, q


def test_index_embed_only_completa_o_float32(origem: Path, tmp_path: Path) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    cfg = load_config(clone)
    sync(cfg)
    assert _linhas(cfg)["grosseiros"] > 0
    index_project(cfg, embed_only=True)
    assert _linhas(cfg)["grosseiros"] == 0


def test_hook_e_touch_nao_reembutem_o_que_o_sync_deixou_grosseiro(origem: Path, tmp_path: Path, textos: list[str]) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    cfg = load_config(clone)
    sync(cfg)
    textos.clear()
    index_project(cfg, source="hook:post-commit")
    assert textos == [] and _linhas(cfg)["grosseiros"] > 0


# ── segurança ───────────────────────────────────────────────────────────
def test_shard_que_cita_chunk_de_arquivo_bloqueado_ou_apagado_nao_grava_nada(origem: Path, tmp_path: Path) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    # a origem tinha m3.py indexado e com vetor; no clone ele agora é um arquivo bloqueado (nome sensível)
    (clone / "m3.py").unlink()
    (clone / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nx\n", encoding="utf-8")
    (clone / "m4.py").unlink()  # e m4.py foi apagado
    cfg = load_config(clone)
    sync(cfg)
    with open_db(cfg.db_path, read_only=True) as c:
        orfaos = c.execute(
            "SELECT COUNT(*) FROM embeddings e LEFT JOIN chunks ch ON ch.id = e.chunk_id WHERE ch.id IS NULL"
        ).fetchone()[0]
        conteudo = "\n".join(r[0] for r in c.execute("SELECT content FROM chunks"))
    n = _linhas(cfg)
    assert orfaos == 0 and n["embeddings"] <= n["chunks"]
    assert "Servico4" not in conteudo and "PRIVATE KEY" not in conteudo


def test_o_import_nao_grava_conteudo(origem: Path, tmp_path: Path) -> None:
    clone = _clonar(origem, tmp_path / "clone")
    cfg = load_config(clone)
    index_project(cfg, embed=False)
    with open_db(cfg.db_path) as conn:
        conteudo_antes = [tuple(r) for r in conn.execute("SELECT id, content FROM chunks ORDER BY id")]
        embeddings_import.import_embeddings(cfg, conn)
        conteudo_depois = [tuple(r) for r in conn.execute("SELECT id, content FROM chunks ORDER BY id")]
    assert conteudo_antes == conteudo_depois
