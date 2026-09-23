from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ragx import githooks
from ragx.core.errors import UsageError

PREFIX = '"/opt/ragx/bin/ragx"'


def _repo(root: Path) -> Path:
    if subprocess.run(["git", "init", "-q"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    return root


def _hook(root: Path, event: str) -> Path:
    return root / ".git" / "hooks" / event


def test_instala_os_tres_eventos(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    written = githooks.install(root, PREFIX)
    assert sorted(p.name for p in written) == sorted(githooks.EVENTS)
    body = _hook(root, "post-checkout").read_text(encoding="utf-8")
    assert body.startswith("#!/bin/sh\n")
    assert f"# ragx-hook-start {root.resolve().as_posix()}" in body
    assert "hook-run post-checkout" in body
    assert 'RAGX_SKIP_HOOK' in body
    assert githooks.state(root)["installed"] is True


def test_instalar_duas_vezes_nao_duplica(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    githooks.install(root, PREFIX)
    githooks.install(root, '"/outro/ragx"')
    body = _hook(root, "post-commit").read_text(encoding="utf-8")
    assert body.count("ragx-hook-start") == 1
    assert "/outro/ragx" in body


def test_preserva_hook_de_outra_ferramenta(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    hook = _hook(root, "post-commit")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho outra-ferramenta\n", encoding="utf-8")
    githooks.install(root, PREFIX)
    assert "echo outra-ferramenta" in hook.read_text(encoding="utf-8")
    githooks.uninstall(root)
    body = hook.read_text(encoding="utf-8")
    assert "echo outra-ferramenta" in body and "ragx-hook-start" not in body


def test_desinstalar_apaga_arquivo_que_so_tinha_o_bloco(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    githooks.install(root, PREFIX)
    githooks.uninstall(root)
    assert not _hook(root, "post-merge").exists()
    assert githooks.state(root)["installed"] is False


def test_dois_projetos_no_mesmo_repo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    a, b = root / "a", root / "b"
    a.mkdir()
    b.mkdir()
    githooks.install(a, PREFIX)
    githooks.install(b, PREFIX)
    body = _hook(root, "post-commit").read_text(encoding="utf-8")
    assert body.count("ragx-hook-start") == 2
    githooks.uninstall(a)
    assert githooks.installed(a) is False
    assert githooks.installed(b) is True


def test_raiz_com_espaco_fica_entre_aspas(tmp_path: Path) -> None:
    root = tmp_path / "Fulano Silva" / "proj"
    root.mkdir(parents=True)
    _repo(root)
    githooks.install(root, PREFIX)
    body = _hook(root, "post-commit").read_text(encoding="utf-8")
    assert f'--root "{root.resolve().as_posix()}"' in body


@pytest.mark.parametrize("bad", ['a"b', "a$b", "a`b"])
def test_raiz_com_caractere_de_shell_e_recusada(tmp_path: Path, bad: str) -> None:
    root = tmp_path / bad
    try:
        root.mkdir()
    except OSError:
        pytest.skip("sistema de arquivos não aceita o nome")
    _repo(root)
    with pytest.raises(UsageError):
        githooks.install(root, PREFIX)


def test_fora_de_repo_e_erro_de_uso(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        githooks.install(tmp_path, PREFIX)
    assert githooks.installed(tmp_path) is None


def test_respeita_core_hookspath(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=root, check=True)
    githooks.install(root, PREFIX)
    assert (root / ".husky" / "post-commit").exists()


@pytest.mark.parametrize(
    ("event", "args", "expected"),
    [
        ("post-checkout", ["a", "b", "1"], True),
        ("post-checkout", ["a", "b", "0"], False),
        ("post-checkout", [], False),
        ("post-commit", [], True),
        ("post-merge", ["0"], True),
    ],
)
def test_should_run(event: str, args: list[str], expected: bool) -> None:
    assert githooks.should_run(event, args) is expected
