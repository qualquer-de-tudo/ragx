"""Nenhum processo filho do RAGX pode abrir janela de terminal no Windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ragx import githooks, procs

pytestmark = pytest.mark.unit

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def test_no_windows_a_flag_e_create_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert procs.quiet_kwargs() == {"creationflags": CREATE_NO_WINDOW}


def test_fora_do_windows_nao_muda_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert procs.quiet_kwargs() == {}


def test_run_quiet_repassa_argumentos_e_soma_a_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    visto: dict[str, Any] = {}

    def falso(argv: list[str], **kw: Any) -> str:
        visto["argv"], visto["kw"] = argv, kw
        return "ok"

    monkeypatch.setattr(subprocess, "run", falso)
    assert procs.run_quiet(["git", "status"], cwd="x", capture_output=True) == "ok"
    assert visto["argv"] == ["git", "status"]
    assert visto["kw"]["cwd"] == "x"
    assert visto["kw"]["creationflags"] & CREATE_NO_WINDOW


def test_run_quiet_preserva_flags_de_quem_chamou(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    visto: dict[str, Any] = {}
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: visto.update(kw))
    procs.run_quiet(["x"], creationflags=0x200)
    assert visto["creationflags"] == 0x200 | CREATE_NO_WINDOW


def test_indexacao_do_hook_nao_e_detached_no_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DETACHED_PROCESS deixa o processo sem console, e cada `git` que ele roda
    ganha uma janela nova. CREATE_NO_WINDOW dá um console oculto que os filhos herdam."""
    monkeypatch.setattr(sys, "platform", "win32")
    chamadas: list[dict[str, Any]] = []

    class FakePopen:
        def __init__(self, argv: list[str], **kw: Any) -> None:
            chamadas.append(kw)

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    githooks.spawn_index(tmp_path, "post-commit")
    flags = chamadas[0]["creationflags"]
    assert flags & CREATE_NO_WINDOW
    assert not flags & DETACHED_PROCESS


def test_nenhum_subprocess_run_direto_no_pacote() -> None:
    """Chamada nova a `subprocess.run` abriria janela no Windows; use `procs.run_quiet`."""
    raiz = Path(procs.__file__).parent
    infratores = [
        p.relative_to(raiz).as_posix()
        for p in raiz.rglob("*.py")
        if p.name != "procs.py" and "subprocess.run(" in p.read_text(encoding="utf-8")
    ]
    assert not infratores, f"use ragx.procs.run_quiet em vez de subprocess.run: {infratores}"
