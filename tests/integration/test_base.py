"""Fase 11 — conhecimento base compartilhado entre projetos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.base import source as base_source
from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.search.service import search
from ragx.storage.db import open_db
from ragx.sync import serialize

pytestmark = pytest.mark.integration

GUARDRAIL = """# Guardrails

O agente NUNCA executa migracao de banco sem aprovacao explicita do humano.
Toda acao destrutiva exige confirmacao registrada no decision log.
"""

PADRAO = """# Padroes de arquitetura

Camadas: controller -> action -> service -> repository.
DTO sempre imutavel. Nenhuma query dentro de controller.
"""


@pytest.fixture()
def cenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    """Um projeto, uma fonte base local e um HOME isolado."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    fonte = tmp_path / "regras-da-casa"
    (fonte / "ai").mkdir(parents=True)
    (fonte / "ai" / "guardrails.md").write_text(GUARDRAIL, encoding="utf-8")
    (fonte / "core").mkdir()
    (fonte / "core" / "patterns.md").write_text(PADRAO, encoding="utf-8")

    root = tmp_path / "projeto"
    root.mkdir()
    (root / "ragx.toml").write_text(
        '[project]\nname = "p"\nid = "p"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n\n'
        f'[hub]\npath = "{(home / ".ragx" / "hub").as_posix()}"\n\n'
        # O projeto DECLARA a fonte. Instalar na máquina não basta.
        f'[base]\nsources = ["{fonte.as_posix()}"]\n',
        encoding="utf-8",
    )
    (root / "app.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    return load_config(root), fonte


def test_fonte_local_e_indexada_sob_prefixo(cenario: tuple) -> None:
    cfg, fonte = cenario
    r = base_source.add(cfg, str(fonte), name="casa")
    assert r.files == 2

    index_project(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = [
            row[0] for row in conn.execute("SELECT rel_path FROM documents ORDER BY rel_path")
        ]
    assert "@base/casa/ai/guardrails.md" in caminhos
    assert "@base/casa/core/patterns.md" in caminhos
    assert "app.py" in caminhos


def test_conhecimento_base_aparece_na_busca(cenario: tuple) -> None:
    cfg, fonte = cenario
    base_source.add(cfg, str(fonte), name="casa")
    index_project(cfg)

    out = search(cfg, "migracao de banco sem aprovacao", mode="keyword", limit=10)
    achados = [r.document_path for r in out.results]
    assert any(p.startswith("@base/casa/") for p in achados), achados


def test_base_nao_entra_no_knowledge_versionado(cenario: tuple) -> None:
    """O Git recebe a RECEITA, não o conteúdo de terceiro."""
    cfg, fonte = cenario
    base_source.add(cfg, str(fonte), name="casa")
    index_project(cfg)
    serialize.serialize(cfg)

    versionados = [
        json.loads(p.read_text(encoding="utf-8"))["rel_path"]
        for p in (cfg.knowledge_dir / "documents").glob("*.json")
    ]
    assert versionados, "nada foi serializado"
    assert not any(p.startswith("@base/") for p in versionados), versionados
    assert "app.py" in versionados


def test_desabilitar_tira_os_documentos_do_indice(cenario: tuple) -> None:
    cfg, fonte = cenario
    base_source.add(cfg, str(fonte), name="casa")
    index_project(cfg)

    base_source.set_enabled(cfg, "casa", False)
    index_project(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE rel_path LIKE '@base/%'"
        ).fetchone()[0]
    assert n == 0


def test_segredo_em_fonte_base_e_bloqueado(cenario: tuple) -> None:
    """Conteúdo de terceiro passa pelo MESMO gate. Sem exceção.

    É a razão de a base entrar por `iter_files`: um repositório de regras com
    um `.env` esquecido não contamina o índice de quem o instalou.
    """
    cfg, fonte = cenario
    (fonte / ".env").write_text(
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n",
        encoding="utf-8",
    )
    base_source.add(cfg, str(fonte), name="casa")
    r = index_project(cfg)

    assert r.stats.blocked >= 1
    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = [row[0] for row in conn.execute("SELECT rel_path FROM documents")]
    assert "@base/casa/.env" not in caminhos
    out = search(cfg, "AWS_SECRET_ACCESS_KEY", mode="keyword", limit=10)
    assert not out.results


def test_registro_viaja_no_git_e_sync_reproduz(cenario: tuple) -> None:
    cfg, fonte = cenario
    base_source.add(cfg, str(fonte), name="casa")
    index_project(cfg)
    serialize.serialize(cfg)

    manifesto = cfg.knowledge_dir / serialize.BASE_MANIFEST
    # Fonte local não viaja (o colega não tem esse caminho), mas o manifesto é
    # escrito assim que o projeto DECLARA uma origem em ragx.toml.
    assert base_source.declared_for(cfg) == [] or manifesto.is_file()

    cfg.base.sources = ["https://example.invalid/regras.git"]
    serialize.serialize(cfg)
    data = json.loads(manifesto.read_text(encoding="utf-8"))
    assert data["required"] == ["https://example.invalid/regras.git"]
    assert base_source.declared_for(cfg)[0]["origin"].endswith("regras.git")


def test_fonte_instalada_mas_nao_declarada_nao_e_indexada(cenario: tuple) -> None:
    """A regra que impede uma fonte de contaminar todo projeto da máquina.

    `~/.ragx/base/` é global. Se bastasse estar instalada, um `ragx base add`
    num projeto mudaria em silêncio o índice de todos os outros — e ninguém
    descobriria até a busca devolver a regra de outro contexto.
    """
    cfg, fonte = cenario
    outra = fonte.parent / "regras-alheias"
    (outra).mkdir()
    (outra / "x.md").write_text("# Regra de outro time\n", encoding="utf-8")

    base_source.add(cfg, str(outra), name="alheias")
    assert any(s.name == "alheias" for s in base_source.load_registry(cfg))
    assert "alheias" not in [n for n, _ in base_source.active_roots(cfg)]

    index_project(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE rel_path LIKE '@base/alheias/%'"
        ).fetchone()[0]
    assert n == 0


def test_caminho_base_e_reconhecivel() -> None:
    assert base_source.is_base_path("@base/agents/ai/guardrails.md")
    assert not base_source.is_base_path("src/app.py")
    assert base_source.split_base_path("@base/agents/ai/x.md") == ("agents", "ai/x.md")
