from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ragx import gitinfo


def _repo(root: Path) -> Path:
    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "c1"], cwd=root, check=True)
    return root


def test_fora_de_repo_devolve_none(tmp_path: Path) -> None:
    assert gitinfo.read_state(tmp_path) is None


def test_estado_limpo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    st = gitinfo.read_state(root)
    assert st is not None
    assert st.branch == "main"
    assert len(st.commit) == 40
    assert st.dirty is False


def test_estado_sujo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "a.txt").write_text("b\n", encoding="utf-8")
    st = gitinfo.read_state(root)
    assert st is not None and st.dirty is True


def test_head_destacado_tem_branch_none(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    head = gitinfo.git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "checkout", "-q", "--detach", head], cwd=root, check=True)
    st = gitinfo.read_state(root)
    assert st is not None and st.branch is None and st.commit == head


def test_repo_sem_commit_devolve_none(tmp_path: Path) -> None:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    assert gitinfo.read_state(tmp_path) is None


def test_git_sempre_passa_no_optional_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git status` sem esta flag refresca e grava `.git/index` — rodado em
    background (hook, watcher) ao mesmo tempo que um `git rebase`/`checkout`/
    `commit` do usuário, essa escrita pode colidir com a dele. Verifica o
    argv de verdade que chega ao `subprocess.run`, não só o comportamento."""
    capturado: list[list[str]] = []
    real_run = subprocess.run

    def _fake_run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        capturado.append(list(argv))
        return real_run(argv, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gitinfo.git(tmp_path, "rev-parse", "--show-toplevel")

    assert capturado, "subprocess.run não foi chamado"
    argv = capturado[0]
    assert argv[0] == "git"
    assert "--no-optional-locks" in argv
    assert argv.index("--no-optional-locks") == 1, (
        "a flag precisa vir logo após 'git', antes do subcomando"
    )


def test_read_state_usa_uma_unica_chamada_ao_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    chamadas: list[tuple[str, ...]] = []
    original = gitinfo.run_quiet

    def espia(cmd, *a, **k):  # type: ignore[no-untyped-def]
        chamadas.append(tuple(cmd))
        return original(cmd, *a, **k)

    monkeypatch.setattr(gitinfo, "run_quiet", espia)
    st = gitinfo.read_state(root)
    assert st is not None and st.branch == "main" and len(st.commit) == 40
    assert len(chamadas) == 1, chamadas


def test_read_state_sujo_com_arquivo_novo_nao_rastreado(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "novo.txt").write_text("n\n", encoding="utf-8")
    st = gitinfo.read_state(root)
    assert st is not None and st.dirty is True and st.branch == "main"


# ── worktrees (RAGX-0170) ───────────────────────────────────────────────
def test_common_dir_e_worktrees_fora_de_git(tmp_path: Path) -> None:
    assert gitinfo.common_dir(tmp_path) is None
    assert gitinfo.worktrees(tmp_path) == []


def test_common_dir_e_o_mesmo_no_principal_e_no_worktree(tmp_path: Path) -> None:
    principal = _repo(tmp_path / "principal") if (tmp_path / "principal").mkdir() is None else tmp_path
    novo = tmp_path / "irmao"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "outra", str(novo)], cwd=principal, check=True)
    # num worktree `.git` é um ARQUIVO; ainda assim a pasta comum é a do repositório principal
    assert (novo / ".git").is_file()
    esperado = (principal / ".git").resolve()
    assert gitinfo.common_dir(principal) == esperado
    assert gitinfo.common_dir(novo) == esperado


def test_worktrees_lista_o_principal_primeiro_com_branch_e_head(tmp_path: Path) -> None:
    principal = _repo(tmp_path / "principal") if (tmp_path / "principal").mkdir() is None else tmp_path
    novo = tmp_path / "irmao"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "outra", str(novo)], cwd=principal, check=True)
    solto = tmp_path / "solto"
    subprocess.run(["git", "worktree", "add", "-q", "--detach", str(solto)], cwd=principal, check=True)
    lista = gitinfo.worktrees(novo)  # perguntando de DENTRO de um worktree irmão
    assert [w.path.resolve() for w in lista] == [principal.resolve(), novo.resolve(), solto.resolve()]
    assert [w.branch for w in lista] == ["main", "outra", None]
    assert [w.detached for w in lista] == [False, False, True]
    assert all(w.head and len(w.head) == 40 for w in lista)
