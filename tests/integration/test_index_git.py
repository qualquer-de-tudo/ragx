"""Índice sem mudança: perguntar ao git o que mudou, em vez de varrer todos os arquivos (RAGX-0198).

A regra que estes testes cobram: o conjunto indexado pelo caminho do git é IDÊNTICO ao da varredura
completa. Cada cenário indexa pelo git e depois confere de dois jeitos: (1) uma cópia da mesma árvore,
indexada com `full_scan=True`, chega ao mesmo banco; (2) uma varredura completa logo em seguida, na
mesma árvore, não acha nada para mudar. E todo recuo para a varredura listado na tarefa tem teste.

Ver `task/fase-23-pos-lancamento/RAGX-0198-*.md`.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from ragx import gitinfo
from ragx.config import load_config
from ragx.indexing import pipeline
from ragx.indexing.pipeline import META_GIT, index_paths, index_project

pytestmark = pytest.mark.integration

TOML = (
    '[project]\nname = "t"\nid = "t"\n\n'
    '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n\n'
    "[index]\nmax_file_bytes = 4000\njobs = 1\n"
)
# segredo falso de propósito (padrão AWS de documentação)
SEGREDO = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'


def _git(raiz: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True, text=True, encoding="utf-8")
    return r.stdout


def _escrever(raiz: Path, arquivos: dict[str, str | bytes]) -> None:
    for rel, conteudo in arquivos.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(conteudo, bytes):
            p.write_bytes(conteudo)
        else:
            p.write_text(conteudo, encoding="utf-8")


def _repo(raiz: Path, extra: dict[str, str | bytes] | None = None, toml: str = TOML) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=raiz, capture_output=True).returncode != 0:
        pytest.skip("git indisponível")
    for chave, valor in (("user.email", "t@t"), ("user.name", "t"), ("core.autocrlf", "false"),
                         ("core.quotepath", "true")):
        _git(raiz, "config", chave, valor)
    _escrever(raiz, {
        "ragx.toml": toml,
        ".gitignore": ".ragx/\nignorada/\n*.log\nrascunho*.py\nbuild/\n!build/keep.py\n",
        ".ragignore": "!rascunho_ok.py\n",
        "src/a.py": "def a():\n    return 1\n",
        "src/b.py": "def b():\n    return 2\n",
        "src/c.py": "def c():\n    return 3\n",
        "docs/d.md": "# D\n\n## S\n\ntexto\n",
        "pasta com espaço/ação.py": "def acao():\n    return 'á'\n",
        "crlf.py": "def crlf():\r\n    return 1\r\n",
        "ignorada/x.py": "def x():\n    return 0\n",
        "rascunho_ok.py": "def r():\n    return 'ragx indexa, git ignora'\n",
        "rascunho_nao.py": "def n():\n    return 0\n",
        "build/keep.py": "def keep():\n    return 'negação em pasta ignorada'\n",
        "build/out.py": "def out():\n    return 0\n",
        **(extra or {}),
    })
    _git(raiz, "add", "-A")
    _git(raiz, "commit", "-qm", "c1")
    # Arquivo com mtime de agora entra na lista para olhar de novo (pode ter mudado depois do `git status`).
    # Num projeto de verdade quase nada tem mtime dos últimos segundos; aqui, tudo teria.
    _envelhecer(raiz)
    return raiz


def _envelhecer(raiz: Path) -> None:
    antigo = time.time() - 600
    for p in raiz.rglob("*"):
        if p.is_file() and ".git" not in p.relative_to(raiz).parts:
            os.utime(p, (antigo, antigo))
    subprocess.run(["git", "update-index", "--refresh", "-q"], cwd=raiz, capture_output=True)


def _index(raiz: Path, **kw: Any) -> pipeline.IndexReport:
    return index_project(load_config(raiz), **kw)


def _estado(raiz: Path) -> dict[str, Any]:
    conn = sqlite3.connect(load_config(raiz).db_path)
    try:
        return {
            "docs": dict(conn.execute("SELECT rel_path, content_hash || ':' || chunker_version FROM documents")),
            "chunks": set(conn.execute(
                "SELECT d.rel_path, c.id FROM chunks c JOIN documents d ON d.id = c.document_id")),
            "vereditos": dict(conn.execute("SELECT rel_path, verdict FROM file_verdicts")),
            "eventos": set(conn.execute("SELECT DISTINCT path, rule_id FROM security_events")),
        }
    finally:
        conn.close()


def _registro(raiz: Path) -> str | None:
    conn = sqlite3.connect(load_config(raiz).db_path)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (META_GIT,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _confere_equivalencia(raiz: Path, copia: Path) -> None:
    """O banco do caminho pelo git é o da varredura completa: na cópia e na mesma árvore."""
    pelo_git = _estado(raiz)
    r = _index(copia, full_scan=True)
    assert r.scan_mode == "full"
    assert _estado(copia) == pelo_git
    depois = _index(raiz, full_scan=True)
    assert (depois.stats.indexed, depois.stats.removed) == (0, 0)
    assert _estado(raiz) == pelo_git


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    raiz = _repo(tmp_path / "p")
    primeira = _index(raiz)
    assert primeira.scan_mode == "full" and primeira.scan_fallback == "sem_commit_guardado"
    assert _registro(raiz) is not None
    return raiz


def _copiar(raiz: Path, destino: Path) -> Path:
    shutil.copytree(raiz, destino, copy_function=shutil.copy2)
    return destino


# ── o conjunto indexado é idêntico ao da varredura ───────────────────────────────────────────────

def test_sem_mudanca_vai_pelo_git_sem_olhar_arquivo(repo: Path) -> None:
    antes = _estado(repo)
    r = _index(repo)
    assert r.scan_mode == "git" and r.scan_fallback is None
    # só o que o git ignora e o RAGX ainda alcança: `rascunho_ok.py` e a pasta `build/` (por causa do `!build/keep.py`)
    assert r.stats.files_seen <= 4
    assert (r.stats.indexed, r.stats.removed) == (0, 0)
    assert _estado(repo) == antes
    assert "rascunho_ok.py" in antes["docs"] and "build/keep.py" in antes["docs"]
    assert "rascunho_nao.py" not in antes["docs"] and "ignorada/x.py" not in antes["docs"]


def test_equivalencia_com_novo_apagado_renomeado_ignorado_binario_grande_e_segredo(
    repo: Path, tmp_path: Path
) -> None:
    copia = _copiar(repo, tmp_path / "copia")
    for raiz in (repo, copia):
        _escrever(raiz, {
            "src/novo.py": "def novo():\n    return 4\n",
            "src/a.py": "def a():\n    return 100\n",
            "ignorada/y.py": "def y():\n    return 0\n",
            "outro.log": "log\n",
            "bin/dado.py": b"\x00\x01\x02binario",
            "grande.py": "x = 1\n" * 2000,
            ".env": "DB_PASSWORD=hunter2hunter2\n",
            "config.py": SEGREDO,
            "pasta com espaço/ação.py": "def acao():\n    return 'ã'\n",
            "crlf.py": "def crlf():\r\n    return 2\r\n",
            "rascunho_ok.py": "def r():\n    return 'mudou e o git nem viu'\n",
            "rascunho_nao.py": "def n():\n    return 1\n",
            "build/keep.py": "def keep():\n    return 'mudou dentro de pasta ignorada'\n",
            "build/novo_keep.py": "def x():\n    return 0\n",
            "acentuação/nova ção.md": "# Título\n\ntexto com acento\n",
        })
        (raiz / "src" / "b.py").unlink()
        _git(raiz, "mv", "src/c.py", "src/c2.py")
        (raiz / "docs" / "d.md").rename(raiz / "docs" / "d2.md")  # renomeado só no disco
    r = _index(repo)
    assert r.scan_mode == "git", r.scan_fallback
    docs = _estado(repo)["docs"]
    assert {"src/novo.py", "src/c2.py", "docs/d2.md", "acentuação/nova ção.md"} <= set(docs)
    assert not {"src/b.py", "src/c.py", "docs/d.md", ".env", "config.py", "grande.py"} & set(docs)
    assert "ignorada/y.py" not in docs and "build/novo_keep.py" not in docs
    _confere_equivalencia(repo, copia)


def test_equivalencia_depois_de_commits(repo: Path, tmp_path: Path) -> None:
    copia = _copiar(repo, tmp_path / "copia")
    for raiz in (repo, copia):
        _escrever(raiz, {"src/a.py": "def a():\n    return 'commitado'\n", "src/d.py": "def d():\n    return 4\n"})
        (raiz / "src" / "b.py").unlink()
        _git(raiz, "add", "-A")
        _git(raiz, "commit", "-qm", "c2")
        _escrever(raiz, {"src/c.py": "def c():\n    return 'sujo depois do commit'\n"})
    r = _index(repo)
    assert r.scan_mode == "git"
    assert r.stats.indexed == 3 and r.stats.removed == 1
    _confere_equivalencia(repo, copia)


def test_troca_de_branch_e_volta(repo: Path, tmp_path: Path) -> None:
    _git(repo, "checkout", "-qb", "outra")
    _escrever(repo, {"src/so_na_outra.py": "def o():\n    return 1\n", "src/a.py": "def a():\n    return 'outra'\n"})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "outra")
    assert _index(repo).scan_mode == "git"
    assert "src/so_na_outra.py" in _estado(repo)["docs"]
    _git(repo, "checkout", "-q", "main")
    r = _index(repo)
    assert r.scan_mode == "git"
    assert "src/so_na_outra.py" not in _estado(repo)["docs"]
    _confere_equivalencia(repo, _copiar(repo, tmp_path / "copia"))


def test_arquivo_sujo_desfeito_com_checkout_volta_ao_conteudo_do_commit(repo: Path, tmp_path: Path) -> None:
    """Sujo numa rodada, limpo na seguinte: o git não aponta mais, mas o índice tinha o conteúdo sujo."""
    original = _estado(repo)["docs"]["src/a.py"]
    _escrever(repo, {"src/a.py": "def a():\n    return 'sujo'\n"})
    assert _index(repo).scan_mode == "git"
    assert _estado(repo)["docs"]["src/a.py"] != original
    _git(repo, "checkout", "--", "src/a.py")
    r = _index(repo)
    assert r.scan_mode == "git"
    assert _estado(repo)["docs"]["src/a.py"] == original
    _confere_equivalencia(repo, _copiar(repo, tmp_path / "copia"))


def test_arquivo_indexado_por_caminho_e_desfeito_entra_na_proxima_rodada(repo: Path, tmp_path: Path) -> None:
    """`touch`/`watch` indexa um conteúdo que o git pode nunca apontar (editado e desfeito entre duas rodadas)."""
    original = _estado(repo)["docs"]["src/a.py"]
    _escrever(repo, {"src/a.py": "def a():\n    return 'editado pelo agente'\n"})
    index_paths(load_config(repo), ["src/a.py"])
    assert _estado(repo)["docs"]["src/a.py"] != original
    _git(repo, "checkout", "--", "src/a.py")
    assert _index(repo).scan_mode == "git"
    assert _estado(repo)["docs"]["src/a.py"] == original
    _confere_equivalencia(repo, _copiar(repo, tmp_path / "copia"))


def test_ignorado_pelo_git_e_indexado_pelo_ragx_que_some(repo: Path, tmp_path: Path) -> None:
    """Arquivo que o git ignora some do disco: ele não aparece mais em lista nenhuma do git."""
    assert "rascunho_ok.py" in _estado(repo)["docs"]
    (repo / "rascunho_ok.py").unlink()
    (repo / "build" / "keep.py").unlink()
    r = _index(repo)
    assert r.scan_mode == "git"
    assert not {"rascunho_ok.py", "build/keep.py"} & set(_estado(repo)["docs"])
    _confere_equivalencia(repo, _copiar(repo, tmp_path / "copia"))


def test_exclusao_global_do_git_e_include_da_config(tmp_path: Path) -> None:
    """O git ignora (exclusão local do repositório e regra de pasta), o RAGX indexa (`include`)."""
    toml = TOML + 'include = ["gerado/**"]\n'
    raiz = _repo(tmp_path / "p", {"gerado/g.py": "def g():\n    return 1\n", "local.py": "def l():\n    return 1\n"},
                 toml=toml)
    (raiz / ".git" / "info" / "exclude").write_text("local.py\n", encoding="utf-8")
    with open(raiz / ".gitignore", "a", encoding="utf-8") as f:
        f.write("gerado/\n")
    _git(raiz, "rm", "-rq", "--cached", "gerado", "local.py")
    _git(raiz, "commit", "-qam", "ignora")
    _index(raiz)
    assert {"gerado/g.py", "local.py"} <= set(_estado(raiz)["docs"])
    copia = _copiar(raiz, tmp_path / "copia")
    for r in (raiz, copia):
        _escrever(r, {"gerado/g.py": "def g():\n    return 2\n", "gerado/novo.py": "def n():\n    return 0\n",
                      "local.py": "def l():\n    return 2\n"})
    rel = _index(raiz)
    assert rel.scan_mode == "git"
    assert "gerado/novo.py" in _estado(raiz)["docs"]
    _confere_equivalencia(raiz, copia)


def test_raiz_em_subpasta_do_repositorio(tmp_path: Path) -> None:
    topo = tmp_path / "mono"
    _repo(topo, {"app/ragx.toml": TOML, "app/m.py": "def m():\n    return 1\n", "fora.py": "def f():\n    return 1\n"})
    app = topo / "app"
    _index(app)
    _escrever(topo, {"app/m.py": "def m():\n    return 2\n", "app/novo.py": "def n():\n    return 1\n",
                     "fora.py": "def f():\n    return 2\n"})
    r = _index(app)
    assert r.scan_mode == "git"
    docs = set(_estado(app)["docs"])
    assert {"m.py", "novo.py"} <= docs and not any(d.startswith(("fora", "app/", "../")) for d in docs)
    depois = _index(app, full_scan=True)
    assert (depois.stats.indexed, depois.stats.removed) == (0, 0)


# ── cada recuo para a varredura completa ─────────────────────────────────────────────────────────

def test_recuo_fora_de_repositorio_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # nada acima conta como repositório
    raiz = tmp_path / "p"
    _escrever(raiz, {"ragx.toml": TOML, "a.py": "def a():\n    return 1\n"})
    _index(raiz)
    r = _index(raiz)
    assert r.scan_mode == "full" and r.scan_fallback == "nao_e_repositorio_git"
    assert _registro(raiz) is None


def test_recuo_sem_git_instalado(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def sem_git(*_a: Any, **_k: Any) -> Any:
        raise FileNotFoundError("git")

    monkeypatch.setattr(gitinfo, "run_quiet", sem_git)
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "sem_git"
    assert _registro(repo) is None  # e a próxima também varre, até o git voltar


def test_recuo_git_que_falha(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = gitinfo._git_indice

    def falha_no_ls_files(root: Path, *args: str) -> tuple[str | None, str | None]:
        return (None, "git_falhou") if args[0] == "ls-files" else original(root, *args)

    monkeypatch.setattr(gitinfo, "_git_indice", falha_no_ls_files)
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "git_falhou"
    assert _registro(repo) is None
    monkeypatch.undo()
    assert _index(repo).scan_fallback == "sem_commit_guardado"
    assert _index(repo).scan_mode == "git"


def test_recuo_git_que_demora(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitinfo, "TIMEOUT_INDICE_S", 1e-9)
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "git_demorou"


def test_recuo_commit_do_indice_sumiu(repo: Path, tmp_path: Path) -> None:
    _escrever(repo, {"src/a.py": "def a():\n    return 'reescrito'\n"})
    _git(repo, "commit", "-qam", "vai sumir")
    _index(repo)  # o índice fica neste commit
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    _escrever(repo, {"src/a.py": "def a():\n    return 'outra história'\n"})
    _git(repo, "commit", "-qam", "reescreve")
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "-q", "--prune=now")
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "commit_do_indice_sumiu"
    assert _registro(repo) is not None  # o commit novo fica registrado: a seguinte volta ao git
    assert _index(repo).scan_mode == "git"
    _confere_equivalencia(repo, _copiar(repo, tmp_path / "copia"))


@pytest.mark.parametrize("mudanca", ["ragignore", "gitignore_aninhado", "max_file_bytes", "chunker", "ruleset"])
def test_recuo_regras_mudaram(repo: Path, mudanca: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if mudanca == "ragignore":
        _escrever(repo, {".ragignore": "!rascunho_ok.py\nsrc/c.py\n"})
    elif mudanca == "gitignore_aninhado":
        _escrever(repo, {"src/.gitignore": "c.py\n"})
    elif mudanca == "max_file_bytes":
        _escrever(repo, {"ragx.toml": TOML.replace("max_file_bytes = 4000", "max_file_bytes = 10")})
    elif mudanca == "chunker":
        from ragx.indexing import verdicts

        monkeypatch.setattr(verdicts, "CHUNKER_VERSION", "outra-versao")
    else:
        from ragx.indexing import verdicts

        monkeypatch.setattr(verdicts, "RULESET_VERSION", "outra-versao")
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "regras_mudaram"
    if mudanca in ("ragignore", "gitignore_aninhado"):
        assert "src/c.py" not in _estado(repo)["docs"]
    # com as regras novas registradas, a seguinte volta ao git
    assert _index(repo).scan_mode == "git"


def test_recuo_submodulo(repo: Path, tmp_path: Path) -> None:
    outro = _repo(tmp_path / "outro", toml=TOML)
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", outro.as_posix(), "sub")
    _git(repo, "commit", "-qm", "submódulo")
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "submodulo"
    assert "sub/src/a.py" in _estado(repo)["docs"]  # a varredura entra no submódulo
    assert _registro(repo) is None  # com `.gitmodules`, nem a próxima confia no git
    assert _index(repo).scan_fallback == "submodulo"


def test_recuo_link_simbolico_rastreado(repo: Path) -> None:
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=repo, input="src/a.py",
                          capture_output=True, text=True, check=True).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},atalho.py")
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "link_simbolico"


def test_recuo_link_simbolico_novo(repo: Path) -> None:
    try:
        os.symlink(repo / "src" / "a.py", repo / "atalho.py")
    except (OSError, NotImplementedError):
        pytest.skip("sem permissão para criar link simbólico")
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "link_simbolico"
    assert "atalho.py" not in _estado(repo)["docs"]


def test_recuo_follow_symlinks(repo: Path) -> None:
    _escrever(repo, {"ragx.toml": TOML + "follow_symlinks = true\n"})
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "follow_symlinks"


def test_recuo_full_scan_e_full(repo: Path) -> None:
    r = _index(repo, full_scan=True)
    assert r.scan_mode == "full" and r.scan_fallback == "full_scan"
    assert r.stats.indexed == 0  # continua incremental
    r = _index(repo, full=True)
    assert r.scan_mode == "full" and r.scan_fallback == "full"
    assert _index(repo).scan_mode == "git"


def test_cli_full_scan(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import re

    from typer.testing import CliRunner

    from ragx.cli.main import app

    monkeypatch.chdir(repo)

    def rodar(*extra: str) -> dict[str, Any]:
        r = CliRunner().invoke(app, ["index", ".", "--json", *extra])
        assert r.exit_code == 0, r.output
        return dict(json.loads(re.sub(r"\x1b\[[0-9;]*m", "", r.output)))

    assert (rodar("--full-scan")["scan_mode"], rodar("--full-scan")["scan_fallback"]) == ("full", "full_scan")
    assert rodar()["scan_mode"] == "git"


def test_recuo_depois_de_rodada_interrompida(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _escrever(repo, {"src/a.py": "def a():\n    return 'interrompido'\n"})

    def quebra(*_a: Any, **_k: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "_handle", quebra)
    with pytest.raises(KeyboardInterrupt):
        _index(repo)
    monkeypatch.undo()
    assert _registro(repo) is None
    r = _index(repo)
    assert r.scan_mode == "full" and r.scan_fallback == "sem_commit_guardado"


def test_recuo_registro_de_outra_raiz(repo: Path, tmp_path: Path) -> None:
    """`.ragx/` copiado de outro lugar: o registro não vale para esta raiz."""
    copia = _copiar(repo, tmp_path / "copia")
    r = _index(copia)
    assert r.scan_mode == "full" and r.scan_fallback == "sem_commit_guardado"


def test_import_de_pacote_apaga_o_registro(repo: Path, tmp_path: Path) -> None:
    from ragx.portability import importer, package

    pacote = tmp_path / "p.rag"
    package.export(load_config(repo), pacote)
    importer.import_package(load_config(repo), pacote, mode="replace")
    assert _registro(repo) is None


@pytest.mark.skipif(sys.platform not in ("win32", "darwin"), reason="só em sistema de arquivos sem caixa")
def test_recuo_caixa_divergente(repo: Path) -> None:
    mud = gitinfo.Mudancas(head="x", sujos=frozenset({"SRC/A.py"}), completo=True)
    cfg = load_config(repo)
    gate = pipeline.SecurityGate(cfg.root)
    plano, motivo = pipeline._planejar(cfg, gate, mud, {"reolhar": []}, {"src/a.py": None})
    assert plano is None and motivo == "caixa_divergente"
