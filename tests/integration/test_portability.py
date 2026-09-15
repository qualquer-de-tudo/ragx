"""Fase 8 — export/import do pacote .rag."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import RagxError, SecurityBlockedError
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project, status
from ragx.portability import importer, package

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios via SSO."""

    def login(self, c):
        """Valida o token."""
        return self.sso.validate(c)
'''

DOC = "# Autenticacao\n\n## Fluxo\n\nO AuthService valida o token.\n"

_TOML = (
    '[project]\nname = "{name}"\nid = "{name}"\n\n'
    '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n'
)


def _project(root: Path, name: str = "origem") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ragx.toml").write_text(_TOML.format(name=name), encoding="utf-8")
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "doc.md").write_text(DOC, encoding="utf-8")
    return root


@pytest.fixture
def origem(tmp_path: Path) -> Path:
    root = _project(tmp_path / "origem")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


@pytest.fixture
def pacote(origem: Path, tmp_path: Path) -> Path:
    alvo = tmp_path / "p.rag"
    package.export(load_config(origem), alvo)
    return alvo


# ── export ──────────────────────────────────────────────────────────────
def test_export_gera_zip_com_manifest_primeiro(pacote: Path) -> None:
    """`rag inspect` precisa ler o manifest sem expandir o pacote."""
    with zipfile.ZipFile(pacote) as z:
        assert z.namelist()[0] == package.MANIFEST


def test_inspect_le_sem_descompactar(pacote: Path) -> None:
    m = package.inspect(pacote)
    assert m["contents"]["documents"] > 0
    assert m["versions"]["chunker"] == "1"


def test_pacote_inclui_conteudo_dos_chunks(pacote: Path) -> None:
    """Ao contrário de knowledge/, o pacote precisa ser autossuficiente."""
    with zipfile.ZipFile(pacote) as z:
        linha = json.loads(z.read("knowledge/chunks.jsonl").decode().splitlines()[0])
    assert linha["content"]


def test_embeddings_em_int8_por_padrao(pacote: Path) -> None:
    with zipfile.ZipFile(pacote) as z:
        model = json.loads(z.read("embeddings/model.json").decode())
        primeiro = json.loads(z.read("embeddings/vectors.jsonl").decode().splitlines()[0])
    assert model["full_vectors"] is False
    assert "f32" not in primeiro and primeiro["q"]


def test_full_vectors_e_opt_in(origem: Path, tmp_path: Path) -> None:
    alvo = tmp_path / "full.rag"
    package.export(load_config(origem), alvo, full_vectors=True)
    with zipfile.ZipFile(alvo) as z:
        primeiro = json.loads(z.read("embeddings/vectors.jsonl").decode().splitlines()[0])
    assert "f32" in primeiro


def test_nenhum_caminho_absoluto_no_pacote(pacote: Path) -> None:
    with zipfile.ZipFile(pacote) as z:
        body = b"".join(z.read(n) for n in z.namelist())
    texto = body.decode("utf-8", "replace")
    for marca in ("C:/Users", "C:\\\\Users", "/home/", "/Users/"):
        assert marca not in texto, f"caminho absoluto vazou: {marca}"


def test_url_do_remote_nao_vai_em_claro(pacote: Path) -> None:
    m = package.inspect(pacote)
    src = m["source"]
    assert "http" not in json.dumps(src), "URL do remote pode conter token"


def test_checksums_cobrem_tudo(pacote: Path) -> None:
    with zipfile.ZipFile(pacote) as z:
        listados = {
            line.split("  ", 1)[1].strip()
            for line in z.read(package.CHECKSUMS).decode().splitlines() if "  " in line
        }
        reais = set(z.namelist()) - {package.MANIFEST, package.CHECKSUMS}
    assert reais <= listados


def test_export_falha_com_segredo(tmp_path: Path) -> None:
    root = _project(tmp_path / "vazado", "vazado")
    # entra pelo gate porque o arquivo é .md (conteúdo em bloco de código)
    cfg = load_config(root)
    index_project(cfg)
    from ragx.storage.db import open_db

    with open_db(cfg.db_path) as conn:
        conn.execute(
            "UPDATE chunks SET content = ? WHERE ordinal = 0",
            ('KEY = "AKIAIOSFODNN7EXAMPLE"',),
        )
        conn.commit()
    with pytest.raises(SecurityBlockedError, match="Nada foi gravado"):
        package.export(cfg, tmp_path / "x.rag")
    assert not (tmp_path / "x.rag").exists()


def test_export_sem_force(tmp_path: Path) -> None:
    import inspect as _inspect

    assinatura = _inspect.signature(package.export)
    assert "force" not in assinatura.parameters, "não pode existir --force para achado crítico"


# ── import ──────────────────────────────────────────────────────────────
def _destino(tmp_path: Path, name: str = "origem") -> Path:
    root = tmp_path / "destino"
    root.mkdir(parents=True, exist_ok=True)
    (root / "ragx.toml").write_text(_TOML.format(name=name), encoding="utf-8")
    return root


def test_round_trip_reproduz_o_conhecimento(origem: Path, pacote: Path, tmp_path: Path) -> None:
    dst = _destino(tmp_path)
    cfg_dst = load_config(dst)
    r = importer.import_package(cfg_dst, pacote)
    origem_stats = status(load_config(origem))
    assert r.applied["documents"] == origem_stats["documents"]
    assert r.applied["chunks"] == origem_stats["chunks"]
    assert r.applied["entities"] > 0 and r.applied["relations"] > 0


def test_busca_funciona_apos_import_sem_reindexar(pacote: Path, tmp_path: Path) -> None:
    from ragx.search.service import search

    dst = _destino(tmp_path)
    cfg = load_config(dst)
    importer.import_package(cfg, pacote)
    out = search(cfg, "autenticacao", mode="hybrid", limit=5)
    assert out.results


def test_embeddings_sao_importados_com_modelo_igual(pacote: Path, tmp_path: Path) -> None:
    dst = _destino(tmp_path)
    r = importer.import_package(load_config(dst), pacote)
    assert r.applied["embeddings"] > 0, "modelo idêntico devia aceitar os vetores"


def test_modelo_diferente_degrada_com_aviso(pacote: Path, tmp_path: Path) -> None:
    dst = tmp_path / "outro"
    dst.mkdir()
    (dst / "ragx.toml").write_text(
        '[project]\nname = "outro"\nid = "outro"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 512\nversioned_dim = 256\n',
        encoding="utf-8",
    )
    r = importer.import_package(load_config(dst), pacote)
    assert r.applied["embeddings"] == 0
    assert any("modelo de embedding" in w for w in r.warnings)
    assert r.applied["chunks"] > 0, "o resto do conhecimento continua entrando"


def test_skip_embeddings(pacote: Path, tmp_path: Path) -> None:
    dst = _destino(tmp_path)
    r = importer.import_package(load_config(dst), pacote, skip_embeddings=True)
    assert r.applied["embeddings"] == 0


def test_zip_slip_e_rejeitado(tmp_path: Path) -> None:
    mau = tmp_path / "mau.rag"
    with zipfile.ZipFile(mau, "w") as z:
        z.writestr(package.MANIFEST, json.dumps({"schema_version": 1, "versions": {}}))
        z.writestr("../../etc/passwd", "root:x:0:0")
    with pytest.raises(SecurityBlockedError, match="zip-slip"):
        importer.verify(mau)


def test_caminho_absoluto_no_zip_e_rejeitado(tmp_path: Path) -> None:
    mau = tmp_path / "abs.rag"
    with zipfile.ZipFile(mau, "w") as z:
        z.writestr(package.MANIFEST, json.dumps({"schema_version": 1, "versions": {}}))
        z.writestr("/etc/shadow", "x")
    with pytest.raises(SecurityBlockedError):
        importer.verify(mau)


def test_checksum_corrompido_e_rejeitado(pacote: Path, tmp_path: Path) -> None:
    adulterado = tmp_path / "adulterado.rag"
    with zipfile.ZipFile(pacote) as src, zipfile.ZipFile(adulterado, "w") as dst:
        for n in src.namelist():
            body = src.read(n)
            if n == "knowledge/entities.json":
                body = b"[]\n"  # altera sem atualizar o checksum
            dst.writestr(n, body)
    with pytest.raises(SecurityBlockedError, match="checksum"):
        importer.verify(adulterado)


def test_pacote_sem_manifest_e_rejeitado(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio.rag"
    with zipfile.ZipFile(vazio, "w") as z:
        z.writestr("knowledge/x.json", "{}")
    with pytest.raises(RagxError, match="manifest"):
        importer.verify(vazio)


def test_schema_futuro_e_rejeitado(tmp_path: Path) -> None:
    futuro = tmp_path / "futuro.rag"
    with zipfile.ZipFile(futuro, "w") as z:
        z.writestr(package.MANIFEST, json.dumps({"schema_version": 99, "versions": {}}))
    dst = _destino(tmp_path)
    with pytest.raises(RagxError, match="atualize"):
        importer.compatibility(load_config(dst), importer.verify(futuro))


def test_import_nao_escreve_fora_do_projeto(pacote: Path, tmp_path: Path) -> None:
    dst = _destino(tmp_path)
    antes = {p for p in tmp_path.rglob("*") if p.is_file()}
    importer.import_package(load_config(dst), pacote)
    novos = {p for p in tmp_path.rglob("*") if p.is_file()} - antes
    for p in novos:
        assert dst in p.parents, f"escreveu fora do projeto: {p}"


def test_merge_preserva_o_local(origem: Path, pacote: Path, tmp_path: Path) -> None:
    """Conflito de id: o local venceu, porque foi derivado do código real."""
    dst = _project(tmp_path / "destino", "origem")
    cfg = load_config(dst)
    index_project(cfg)
    local = status(cfg)["chunks"]
    r = importer.import_package(cfg, pacote, mode="merge")
    assert r.applied["documents"] == 0, "documentos locais deveriam ter vencido"
    assert status(cfg)["chunks"] >= local


def test_regras_desabilitadas_geram_aviso(origem: Path, tmp_path: Path) -> None:
    cfg = load_config(origem)
    cfg.security.disabled_rules = ["aws-access-key-id"]
    alvo = tmp_path / "fraco.rag"
    package.export(cfg, alvo)
    dst = _destino(tmp_path)
    avisos, _ = importer.compatibility(load_config(dst), package.inspect(alvo))
    assert any("desabilitada" in w for w in avisos)
