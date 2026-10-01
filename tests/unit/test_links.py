"""`is_link`: symlink OU junction do Windows, e só isso."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ragx.security import links
from ragx.security.links import is_link

pytestmark = pytest.mark.unit


def test_diretorio_comum_nao_e_link(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    assert is_link(tmp_path / "d") is False


def test_caminho_inexistente_devolve_falso_sem_lancar(tmp_path: Path) -> None:
    assert is_link(tmp_path / "nao-existe") is False


def test_link_de_verdade_e_link(tmp_path: Path) -> None:
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(alvo), str(tmp_path / "l"))
    else:
        (tmp_path / "l").symlink_to(alvo, target_is_directory=True)
    assert is_link(tmp_path / "l") is True
    assert is_link(alvo) is False


def test_aceita_direntry(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    entry = next(e for e in os.scandir(tmp_path) if e.name == "d")
    assert is_link(entry) is False


def test_reparse_point_que_nao_e_junction_nao_conta(monkeypatch: pytest.MonkeyPatch) -> None:
    """OneDrive (arquivos sob demanda) e AppExecLink também são reparse points."""
    monkeypatch.setattr(links.sys, "platform", "win32")
    monkeypatch.setattr(links.os.path, "islink", lambda p: False)
    nuvem = 0x9000001A  # IO_REPARSE_TAG_CLOUD_FILES
    monkeypatch.setattr(links.os, "lstat", lambda p: SimpleNamespace(st_reparse_tag=nuvem))
    assert is_link("qualquer") is False
    mount = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
    monkeypatch.setattr(links.os, "lstat", lambda p: SimpleNamespace(st_reparse_tag=mount))
    assert is_link("qualquer") is True
