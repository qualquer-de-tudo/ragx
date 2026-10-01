"""Aquecimento do servidor MCP: carrega em segundo plano, nunca derruba (RAGX-0142)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from ragx import embeddings
from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.mcp import warmup
from ragx.mcp.server import build_server

pytestmark = pytest.mark.integration

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


@pytest.fixture()
def cfg(tmp_path: Path):  # type: ignore[no-untyped-def]
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    (tmp_path / "a.py").write_text("def autenticar():\n    return 1\n", encoding="utf-8")
    embeddings.reset_embedder_cache()
    c = load_config(tmp_path)
    index_project(c)
    embeddings.reset_embedder_cache()
    yield c
    embeddings.reset_embedder_cache()


def test_sem_indice_ou_com_warmup_desligado_nao_cria_thread(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    assert warmup.start(load_config(tmp_path)) is None  # sem índice

    (tmp_path / "ragx.toml").write_text(TOML + "\n[mcp]\nwarmup = false\n", encoding="utf-8")
    (tmp_path / ".ragx").mkdir()
    c0 = load_config(tmp_path)
    c0.db_path.write_bytes(b"")
    c = load_config(tmp_path)
    assert c.db_path.exists()
    assert warmup.start(c) is None  # desligado, mesmo com índice


def test_aquecimento_constroi_o_embedder_uma_vez_e_a_busca_concorrente_espera(
    cfg, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    construcoes: list[int] = []
    original = embeddings._construir

    def lenta(c):  # type: ignore[no-untyped-def]
        construcoes.append(1)
        time.sleep(0.3)
        return original(c)

    monkeypatch.setattr(embeddings, "_construir", lenta)
    thread = warmup.start(cfg)
    assert thread is not None and thread.daemon
    # busca disparada DURANTE o aquecimento: resultado correto, mesma construção
    r = asyncio.run(build_server(cfg).call_tool("search_hybrid", {"query": "autenticar"}))
    dados = json.loads("".join(b.text for b in r.content))
    assert (dados.get("data", dados))["results"]
    thread.join(5)
    assert len(construcoes) == 1


def test_falha_no_aquecimento_vai_para_o_log_e_nao_derruba(cfg, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    def quebra(c):  # type: ignore[no-untyped-def]
        raise RuntimeError("ollama fora do ar")

    monkeypatch.setattr(embeddings, "_construir", quebra)
    warmup.warm(cfg)  # não propaga
    log = (cfg.state_dir / "logs" / "errors.log").read_text(encoding="utf-8")
    assert "mcp.warmup.embedder" in log and "ollama fora do ar" in log
    # os outros passos continuam: o índice foi carregado mesmo com o embedder quebrado
    monkeypatch.undo()
    r = asyncio.run(build_server(cfg).call_tool("get_dictionary", {}))
    assert r.content
