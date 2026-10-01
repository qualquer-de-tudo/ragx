"""Rotação dos logs `mcp.jsonl` e `cli.jsonl` e `[log] retain_days` (RAGX-0174)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from ragx import diagnostics
from ragx.config import load_config

pytestmark = pytest.mark.unit


def _log(state: Path, nome: str = "mcp.jsonl") -> Path:
    return state / "logs" / nome


def _enche(path: Path, bytes_: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    linha = json.dumps({"ts": "2026-10-01T00:00:00Z", "tool": "x", "pad": "y" * 900}) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        escritos = 0
        while escritos < bytes_:
            f.write(linha)
            escritos += len(linha)


def test_abaixo_do_teto_nao_rotaciona(tmp_path: Path) -> None:
    diagnostics.log_mcp_call(tmp_path, {"tool": "a"})
    diagnostics.log_mcp_call(tmp_path, {"tool": "b"})
    assert len(_log(tmp_path).read_text(encoding="utf-8").splitlines()) == 2
    assert not _log(tmp_path).with_name("mcp.jsonl.1").exists()


def test_passou_do_teto_vira_ponto_1_e_o_log_recomeca_pequeno(tmp_path: Path) -> None:
    _enche(_log(tmp_path), diagnostics.MAX_LOG_BYTES + 1000)
    antes = _log(tmp_path).stat().st_size
    diagnostics.log_mcp_call(tmp_path, {"tool": "nova"})
    novo, velho = _log(tmp_path), _log(tmp_path).with_name("mcp.jsonl.1")
    assert velho.stat().st_size == antes
    linhas = novo.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1 and json.loads(linhas[0])["tool"] == "nova"


def test_o_ponto_1_anterior_e_substituido(tmp_path: Path) -> None:
    velho = _log(tmp_path).with_name("mcp.jsonl.1")
    velho.parent.mkdir(parents=True)
    velho.write_text("MUITO ANTIGO\n", encoding="utf-8")
    _enche(_log(tmp_path), diagnostics.MAX_LOG_BYTES + 10)
    diagnostics.log_mcp_call(tmp_path, {"tool": "x"})
    assert "MUITO ANTIGO" not in velho.read_text(encoding="utf-8")


def test_cli_jsonl_tem_o_mesmo_teto(tmp_path: Path) -> None:
    _enche(_log(tmp_path, "cli.jsonl"), diagnostics.MAX_LOG_BYTES + 10)
    diagnostics.log_cli_call(tmp_path, {"command": "search"})
    assert _log(tmp_path, "cli.jsonl.1").is_file()
    assert len(_log(tmp_path, "cli.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_retain_days_apaga_o_ponto_1_mais_velho_que_isso(tmp_path: Path) -> None:
    velho = _log(tmp_path).with_name("mcp.jsonl.1")
    velho.parent.mkdir(parents=True)
    velho.write_text("x\n", encoding="utf-8")
    antigo = time.time() - 20 * 86400
    os.utime(velho, (antigo, antigo))
    diagnostics.log_mcp_call(tmp_path, {"tool": "a"}, retain_days=14)
    assert not velho.exists()

    recente = _log(tmp_path).with_name("mcp.jsonl.1")
    recente.write_text("x\n", encoding="utf-8")
    ontem = time.time() - 86400
    os.utime(recente, (ontem, ontem))
    diagnostics.log_mcp_call(tmp_path, {"tool": "b"}, retain_days=14)
    assert recente.exists()


def test_retain_days_zero_nao_apaga_nada(tmp_path: Path) -> None:
    velho = _log(tmp_path).with_name("mcp.jsonl.1")
    velho.parent.mkdir(parents=True)
    velho.write_text("x\n", encoding="utf-8")
    antigo = time.time() - 400 * 86400
    os.utime(velho, (antigo, antigo))
    diagnostics.log_mcp_call(tmp_path, {"tool": "a"}, retain_days=0)
    assert velho.exists()


def test_falha_na_rotacao_nunca_vira_falha_do_chamador(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No Windows outro processo pode segurar o arquivo: `PermissionError` é engolido e a escrita segue."""
    _enche(_log(tmp_path), diagnostics.MAX_LOG_BYTES + 10)

    def nega(*_a: object, **_k: object) -> None:
        raise PermissionError("em uso")

    monkeypatch.setattr(os, "replace", nega)
    diagnostics.log_mcp_call(tmp_path, {"tool": "ainda-grava"})  # não levanta
    assert "ainda-grava" in _log(tmp_path).read_text(encoding="utf-8")
    assert not _log(tmp_path).with_name("mcp.jsonl.1").exists()


def test_os_chamadores_passam_o_retain_days_da_configuracao(tmp_path: Path) -> None:
    from ragx import hooklight

    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n\n[log]\nretain_days = 3\n', encoding="utf-8")
    assert load_config(tmp_path).log.retain_days == 3
    assert hooklight.carregar(tmp_path).retain_days == 3
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    assert hooklight.carregar(tmp_path).retain_days == 14
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n\n[log]\nretain_days = "x"\n', encoding="utf-8")
    assert hooklight.carregar(tmp_path).retain_days == 14  # valor inválido: o padrão


def test_o_servidor_mcp_rotaciona_ao_logar(tmp_path: Path) -> None:
    from ragx.indexing.pipeline import index_project
    from ragx.mcp.server import (
        KnowledgeAPI,  # noqa: F401  (garante o import do módulo que chama log_mcp_call)
    )

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg, embed=False)
    _enche(cfg.state_dir / "logs" / "mcp.jsonl", diagnostics.MAX_LOG_BYTES + 10)

    import asyncio

    from ragx.mcp.server import build_server

    asyncio.run(build_server(cfg).call_tool("get_dictionary", {}))
    assert (cfg.state_dir / "logs" / "mcp.jsonl.1").is_file()
    assert (cfg.state_dir / "logs" / "mcp.jsonl").stat().st_size < 10_000
