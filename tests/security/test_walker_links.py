"""O walker não lê fora da raiz do projeto: nem por symlink, nem por junction.

Ameaça A8 (docs/02-seguranca.md). No Windows, uma junction (`mklink /J`, o que o
pnpm cria, e que não exige privilégio) não é symlink para o Python: passava na
guarda do walker e a pasta de fora era percorrida e indexada. O conteúdo ainda
passava pelo Security Gate, mas era leitura fora da raiz.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0149-*.md`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.security


def _link_dir(link: Path, alvo: Path) -> None:
    """Junction no Windows (sem privilégio); symlink nos demais sistemas."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(alvo), str(link))
    else:
        link.symlink_to(alvo, target_is_directory=True)


def _projeto(tmp_path: Path, follow: bool) -> tuple[Path, Path]:
    raiz = tmp_path / "proj"
    fora = tmp_path / "fora"
    (raiz / "src").mkdir(parents=True)
    fora.mkdir()
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n\n'
        f"[index]\nfollow_symlinks = {str(follow).lower()}\n",
        encoding="utf-8",
    )
    (raiz / "src" / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (fora / "notes.md").write_text("# fora\n\nnao deveria entrar\n", encoding="utf-8")
    return raiz, fora


def _indexados(raiz: Path) -> set[str]:
    cfg = load_config(raiz)
    conn = sqlite3.connect(cfg.db_path)
    try:
        return {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    finally:
        conn.close()


@pytest.mark.parametrize("follow", [False, True])
def test_link_para_fora_da_raiz_nao_e_indexado(tmp_path: Path, follow: bool) -> None:
    raiz, fora = _projeto(tmp_path, follow)
    _link_dir(raiz / "linkout", fora)
    index_project(load_config(raiz))
    caminhos = _indexados(raiz)
    assert "src/app.py" in caminhos  # a pasta de dentro continua indexada
    assert not any(p.startswith("linkout/") for p in caminhos), sorted(caminhos)
    assert not any("notes.md" in p for p in caminhos)


def test_link_para_dentro_da_raiz_nao_e_indexado_duas_vezes_por_padrao(tmp_path: Path) -> None:
    raiz, _ = _projeto(tmp_path, follow=False)
    _link_dir(raiz / "alias", raiz / "src")
    index_project(load_config(raiz))
    caminhos = _indexados(raiz)
    assert "src/app.py" in caminhos
    assert not any(p.startswith("alias/") for p in caminhos)


def test_link_para_dentro_da_raiz_com_follow_e_visitado_uma_vez(tmp_path: Path) -> None:
    raiz, _ = _projeto(tmp_path, follow=True)
    _link_dir(raiz / "alias", raiz / "src")
    index_project(load_config(raiz))
    caminhos = {p for p in _indexados(raiz) if p.endswith("app.py")}
    assert len(caminhos) == 1, caminhos  # a mesma pasta, uma vez só


def test_gitignore_dentro_de_link_para_fora_nao_e_lido(tmp_path: Path) -> None:
    from ragx.security.ignore_engine import IgnoreEngine

    raiz, fora = _projeto(tmp_path, follow=False)
    (fora / ".gitignore").write_text("*.py\n", encoding="utf-8")
    _link_dir(raiz / "linkout", fora)
    engine = IgnoreEngine(raiz)
    assert not any("linkout" in n for n in engine.source_names), engine.source_names


# ── sync.rehydrate lê `root / rel` com `rel` vindo de knowledge/documents/*.json ──
def test_rehydrate_nao_le_fora_da_raiz(tmp_path: Path) -> None:
    from ragx.security.gate import SecurityGate
    from ragx.sync.rehydrate import _lines

    raiz, fora = _projeto(tmp_path, follow=False)
    (tmp_path / "fora.txt").write_text("segredo-de-fora\n", encoding="utf-8")
    _link_dir(raiz / "linkout", fora)
    gate = SecurityGate(raiz, policy="strict")
    for rel in ("../fora.txt", str((tmp_path / "fora.txt").resolve()), "linkout/notes.md"):
        assert _lines(raiz, rel, gate, {}) is None, rel
    # o caminho legítimo continua funcionando
    assert _lines(raiz, "src/app.py", gate, {}) is not None
