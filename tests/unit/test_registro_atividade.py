"""RAGX-0125: quem chamou (Claude Code, perfil, sessão) e o que a CLI fez, sem a consulta."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from ragx.cli import main as cli_main
from ragx.clients.claude_hint import record_session_start
from ragx.clients.registry import claude_origin, profile_name
from ragx.diagnostics import log_mcp_call

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("config_dir", "esperado"),
    [
        (None, "padrão"),
        ("", "padrão"),
        (r"C:\Users\x\.claude-empresa", "empresa"),
        ("/home/x/.claude-vitor/", "vitor"),
        ("/home/x/.claude", "padrão"),
        ("/contas/cliente", "cliente"),
    ],
)
def test_nome_do_perfil(config_dir: str | None, esperado: str) -> None:
    assert profile_name(config_dir) == esperado


def test_origem_so_existe_dentro_do_claude_code() -> None:
    assert claude_origin({}) == {}
    assert claude_origin({"CLAUDE_CONFIG_DIR": "/x/.claude-empresa"}) == {}
    assert claude_origin({
        "CLAUDECODE": "1",
        "CLAUDE_CONFIG_DIR": "/x/.claude-empresa",
        "CLAUDE_CODE_SESSION_ID": "0123456789abcdef",
    }) == {"client": "claude-code", "profile": "empresa", "session": "01234567"}


def _linhas(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_chamada_mcp_grava_perfil_e_sessao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude-empresa"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abcdef0123")
    log_mcp_call(tmp_path, {"ts": "t", "tool": "build_context", "ms": 1.0, "project": "p"})
    (linha,) = _linhas(tmp_path / "logs" / "mcp.jsonl")
    assert linha == {"ts": "t", "tool": "build_context", "ms": 1.0, "project": "p",
                     "client": "claude-code", "profile": "empresa", "session": "abcdef01"}


def test_chamada_mcp_fora_do_claude_code_nao_inventa_origem(tmp_path: Path) -> None:
    log_mcp_call(tmp_path, {"ts": "t", "tool": "search_hybrid", "ms": 1.0, "project": "p"})
    (linha,) = _linhas(tmp_path / "logs" / "mcp.jsonl")
    assert "client" not in linha and "profile" not in linha


@pytest.fixture()
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raiz = tmp_path / "loja"
    (raiz / ".ragx").mkdir(parents=True)
    (raiz / ".ragx" / "knowledge.db").write_bytes(b"")
    (raiz / "ragx.toml").write_text('[project]\nname = "loja"\n', encoding="utf-8")
    monkeypatch.chdir(raiz)
    return raiz


def _cli(projeto: Path) -> list[dict]:
    path = projeto / ".ragx" / "logs" / "cli.jsonl"
    return _linhas(path) if path.exists() else []


def test_consulta_no_terminal_grava_o_comando_e_nunca_a_consulta(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ragx", "search", "segredo da consulta", "--limit", "3"])
    cli_main._registrar(time.monotonic(), 0)
    (linha,) = _cli(projeto)
    assert linha["command"] == "search" and linha["ok"] is True and linha["project"] == "loja"
    assert "segredo" not in json.dumps(linha)


def test_comando_do_painel_e_de_manutencao_nao_entram(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ragx", "status", "--json"])
    cli_main._registrar(time.monotonic(), 0)
    monkeypatch.setattr(sys, "argv", ["ragx", "context", "x"])
    monkeypatch.setenv("RAGX_CALLER", "painel")
    cli_main._registrar(time.monotonic(), 0)
    assert _cli(projeto) == []


def test_consulta_que_falhou_fica_marcada(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ragx", "--quiet", "trial"])
    cli_main._registrar(time.monotonic(), 2)
    (linha,) = _cli(projeto)
    assert linha["command"] == "trial" and linha["ok"] is False


def test_inicio_de_sessao_do_claude_vira_evento(projeto: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record_session_start()  # à mão, fora do Claude Code: não é sessão
    assert _cli(projeto) == []

    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(projeto / ".claude-empresa"))
    record_session_start()
    (linha,) = _cli(projeto)
    assert linha["command"] == "session_start" and linha["profile"] == "empresa"
