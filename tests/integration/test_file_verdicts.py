"""Veredito guardado de arquivo fora do índice (`file_verdicts`, RAGX-0139)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_paths, index_project
from ragx.storage.db import get_meta, open_db

pytestmark = pytest.mark.integration

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'

_LEITURAS_DE_SISTEMA = {"ragx.toml", "patterns.yaml", "filenames.yaml", "default_ignore.txt"}


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    for i in range(6):
        (tmp_path / f"d{i}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "blob.xyz").write_bytes(b"\x00\x01\x02" * 50)
    (tmp_path / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nxxx\n", encoding="utf-8")
    (tmp_path / "cert.pem").write_text("-----BEGIN PRIVATE KEY-----\nxxx\n", encoding="utf-8")
    return tmp_path


def _veredictos(raiz: Path) -> dict[str, tuple[str, str | None]]:
    with open_db(load_config(raiz).db_path, read_only=True) as c:
        return {r[0]: (r[1], r[2]) for r in c.execute("SELECT rel_path, verdict, rule_id FROM file_verdicts")}


def _eventos(raiz: Path) -> list[tuple]:
    with open_db(load_config(raiz).db_path, read_only=True) as c:
        return [tuple(r) for r in c.execute("SELECT id, path, rule_id FROM security_events ORDER BY id")]


@pytest.fixture()
def leituras(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lidos: list[str] = []
    original = Path.read_bytes

    def espia(self: Path) -> bytes:
        if self.name not in _LEITURAS_DE_SISTEMA:  # o TOML (`load_config`) e as regras (hash do contexto)
            lidos.append(self.name)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", espia)
    return lidos


def test_segunda_rodada_nao_le_o_que_ja_foi_vetado(proj: Path, leituras: list[str]) -> None:
    cfg = load_config(proj)
    primeira = index_project(cfg, embed=False)
    assert {n for n in leituras if n.endswith(".csv")} == {f"d{i}.csv" for i in range(6)}
    assert _veredictos(proj)["d0.csv"] == ("unsupported", "unsupported")
    assert _veredictos(proj)["blob.xyz"][0] == "binary"
    assert _veredictos(proj)["id_rsa"][0] == "blocked"
    eventos = _eventos(proj)

    leituras.clear()
    segunda = index_project(cfg, embed=False)
    assert leituras == []  # nenhum .csv, binário ou bloqueado foi aberto
    # os contadores e os `security_events` são os mesmos (mesmos ids de linha)
    assert segunda.stats.blocked == primeira.stats.blocked == 2
    assert sorted(segunda.blocked_paths) == sorted(primeira.blocked_paths)
    assert segunda.stats.skipped == primeira.stats.skipped
    assert _eventos(proj) == eventos


def test_arquivo_vetado_que_muda_e_reavaliado(proj: Path, leituras: list[str]) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    (proj / "d0.csv").write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")  # tamanho novo
    leituras.clear()
    index_project(cfg, embed=False)
    assert leituras == ["d0.csv"]  # só ele, e os outros continuam sem leitura


def test_arquivo_removido_apaga_o_veredito(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    assert "d1.csv" in _veredictos(proj)
    (proj / "d1.csv").unlink()
    index_project(cfg, embed=False)
    assert "d1.csv" not in _veredictos(proj)


def test_veredito_vira_documento_quando_o_arquivo_passa_a_ser_suportado(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    assert "d2.csv" in _veredictos(proj)
    (proj / "d2.csv").unlink()
    (proj / "d2.csv").write_bytes(b"x")  # outro tamanho: não bate com o guardado
    (proj / "d3.csv").rename(proj / "d3.md")
    (proj / "d3.md").write_text("# titulo\n\ntexto\n", encoding="utf-8")
    index_project(cfg, embed=False)
    assert "d3.md" not in _veredictos(proj)
    with open_db(cfg.db_path, read_only=True) as c:
        assert c.execute("SELECT 1 FROM documents WHERE rel_path = 'd3.md'").fetchone()


def test_full_descarta_e_reavalia_tudo(proj: Path, leituras: list[str]) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    leituras.clear()
    index_project(cfg, embed=False, full=True)
    assert {n for n in leituras if n.endswith(".csv")} == {f"d{i}.csv" for i in range(6)}
    assert "d0.csv" in _veredictos(proj)  # e o cache foi refeito


def test_dry_run_nao_grava_nem_descarta(proj: Path, leituras: list[str]) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False, dry_run=True)
    assert _veredictos(proj) == {}  # dry_run não grava

    index_project(cfg, embed=False)
    antes = _veredictos(proj)
    assert antes
    leituras.clear()
    index_project(cfg, embed=False, dry_run=True)
    assert _veredictos(proj) == antes  # nem apaga
    assert leituras == []  # mas usa o que existe


def test_contexto_diferente_descarta_o_cache(proj: Path, leituras: list[str]) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    ctx = None
    with open_db(cfg.db_path, read_only=True) as c:
        ctx = get_meta(c, "verdict_ctx")
    assert ctx
    (proj / "ragx.toml").write_text(TOML + "\n[index]\ninclude_unknown = true\n", encoding="utf-8")
    cfg2 = load_config(proj)
    leituras.clear()
    index_project(cfg2, embed=False)
    assert "d0.csv" in leituras  # reavaliou
    with open_db(cfg2.db_path, read_only=True) as c:
        assert get_meta(c, "verdict_ctx") != ctx


def test_index_paths_tambem_usa_e_mantem_o_cache(proj: Path, leituras: list[str]) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    leituras.clear()
    index_paths(cfg, ["d0.csv", "blob.xyz", "id_rsa"], embed=False)
    assert leituras == []
    assert {"d0.csv", "blob.xyz", "id_rsa"} <= set(_veredictos(proj))

    (proj / "d0.csv").unlink()
    index_paths(cfg, ["d0.csv"], embed=False)
    assert "d0.csv" not in _veredictos(proj)
