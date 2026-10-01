"""A fila de edições não é um atalho em volta do Security Gate (RAGX-0141)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing import touchq
from ragx.indexing.pipeline import index_project
from ragx.mcp.server import build_server
from ragx.storage.db import open_db

pytestmark = pytest.mark.security

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'
# segredo falso de propósito (padrão AWS de documentação)
SEGREDO = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'


def _projeto(raiz: Path) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    (raiz / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_project(load_config(raiz))
    return raiz


def _buscar(cfg, write: bool, query: str) -> dict:  # type: ignore[no-untyped-def]
    r = asyncio.run(build_server(cfg, allow_write=write).call_tool("search_hybrid", {"query": query}))
    dados = json.loads("".join(b.text for b in r.content))
    return dados.get("data", dados)


def test_env_e_segredo_enfileirados_nao_entram_no_indice_nem_em_stale_paths(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    (raiz / ".env").write_text("DB_PASSWORD=hunter2hunter2\n", encoding="utf-8")
    (raiz / "config.py").write_text(SEGREDO, encoding="utf-8")
    cfg = load_config(raiz)
    touchq.enqueue(cfg.state_dir, [".env", "config.py"])

    # servidor somente leitura não drena: o que sobra na fila NÃO pode revelar o `.env`
    lido = _buscar(cfg, write=False, query="a")
    assert ".env" not in json.dumps(lido)

    # com escrita: drena, e nada do que o gate bloqueia entra
    escrito = _buscar(cfg, write=True, query="hunter2hunter2")
    assert "hunter2" not in json.dumps(escrito)
    assert ".env" not in json.dumps(escrito)
    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = {r[0] for r in conn.execute("select rel_path from documents")}
        conteudo = "\n".join(r[0] for r in conn.execute("select content from chunks"))
    assert ".env" not in caminhos
    assert "hunter2" not in conteudo
    assert "wJalrXUtnFEMI" not in conteudo


def test_caminho_que_escapa_da_raiz_nunca_entra_na_fila(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    (tmp_path / "fora.txt").write_text("x\n", encoding="utf-8")
    assert touchq.resolve(raiz, "../fora.txt") is None
    assert touchq.resolve(raiz, tmp_path / "fora.txt") is None
    assert touchq.resolve(raiz, "a/../../fora.txt") is None


@pytest.mark.skipif(sys.platform != "win32", reason="junction só no Windows (symlink é coberto em test_touchq)")
def test_junction_para_fora_e_recusada(tmp_path: Path) -> None:
    import _winapi

    raiz = _projeto(tmp_path / "p")
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "s.py").write_text("x = 1\n", encoding="utf-8")
    _winapi.CreateJunction(str(fora), str(raiz / "linkout"))
    assert touchq.resolve(raiz, "linkout/s.py") is None


def test_visible_so_deixa_passar_o_que_o_gate_admite_pelo_nome(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    cfg = load_config(raiz)
    assert touchq.visible(cfg, ["a.py", ".env", "id_rsa", "node_modules/x.js"]) == ["a.py"]
