"""Conjunto-ouro derivado do git, de ponta a ponta num repositório temporário (RAGX-0167)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ragx import gitinfo
from ragx.cli.main import app
from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.search.evaluation import evaluate, load_cases
from ragx.search.gold import derive_cases, render_yaml
from ragx.storage.db import open_db

pytestmark = pytest.mark.integration


def _git(root: Path, *args: str, env: dict | None = None) -> None:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        pytest.skip(f"git indisponível: {r.stderr[:100]}")


def _commit(root: Path, mensagem: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", mensagem)


FUNCAO = 'def {nome}(x):\n    """Calcula {nome}."""\n    total = 0\n    for k in range(x):\n        total += k * 3\n    return total\n'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "g"\nid = "g"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(".ragx/\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "autor-secreto@example.com")
    _git(tmp_path, "config", "user.name", "Autor Secreto")
    (tmp_path / "busca.py").write_text(FUNCAO.format(nome="busca_por_palavra"), encoding="utf-8")
    (tmp_path / "gate.py").write_text(FUNCAO.format(nome="gate_de_seguranca"), encoding="utf-8")
    _commit(tmp_path, "feat(busca): implementa a busca por palavra-chave (RAGX-0001)")
    (tmp_path / "gate.py").write_text(FUNCAO.format(nome="gate_de_seguranca") + "\n# ajuste\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
    _commit(tmp_path, "fix(gate): bloqueia arquivo com segredo no nome\n\nCorpo do commit que não pode sair.")
    (tmp_path / "temp.py").write_text(FUNCAO.format(nome="temporaria"), encoding="utf-8")
    _commit(tmp_path, "chore: arquivo temporário que sera removido")
    (tmp_path / "temp.py").unlink()
    _commit(tmp_path, "chore: remove o arquivo temporário")
    index_project(load_config(tmp_path))
    return tmp_path


def test_log_commits_traz_so_hash_assunto_e_caminhos(repo: Path) -> None:
    commits = gitinfo.log_commits(repo)
    assert commits is not None and len(commits) == 4
    for c in commits:
        assert "autor" not in c.subject.lower() and "corpo" not in c.subject.lower()
    por_assunto = {c.subject: c for c in commits}
    assert por_assunto["fix(gate): bloqueia arquivo com segredo no nome"].files == ("CHANGELOG.md", "gate.py") or set(
        por_assunto["fix(gate): bloqueia arquivo com segredo no nome"].files
    ) == {"CHANGELOG.md", "gate.py"}


def test_log_commits_fora_de_git_devolve_none(tmp_path: Path) -> None:
    assert gitinfo.log_commits(tmp_path) is None


def test_derive_cases_e_evaluate_rodam_sobre_o_repo(repo: Path) -> None:
    cfg = load_config(repo)
    commits = gitinfo.log_commits(repo)
    assert commits is not None
    with open_db(cfg.db_path, read_only=True) as conn:
        indexados = {r["rel_path"]: r["doc_kind"] for r in conn.execute("SELECT rel_path, doc_kind FROM documents")}
    r = derive_cases(commits, indexados)
    consultas = {c.query: c for c in r.cases}
    assert "implementa a busca por palavra-chave" in consultas
    assert "bloqueia arquivo com segredo no nome" in consultas
    assert consultas["bloqueia arquivo com segredo no nome"].relevant_paths == ("gate.py",)  # o CHANGELOG sai
    # `temp.py` foi apagado depois: não está no índice, então o commit que o criou não gera caso
    assert r.funnel.sem_arquivo_indexado >= 1
    # o avaliador roda sobre o arquivo gerado
    arq = repo / "gold.yaml"
    arq.write_text(render_yaml(r, "abc"), encoding="utf-8")
    metricas = evaluate(cfg, load_cases(arq), ("keyword",))
    assert metricas[0].cases == len(r.cases) and metricas[0].by_class == {"git": (metricas[0].by_class["git"][0], len(r.cases))}


def test_comando_gold_build_e_deterministico_e_nao_vaza_autor_nem_corpo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    runner = CliRunner()
    r = runner.invoke(app, ["gold", "build", "--dry-run"])
    assert r.exit_code == 0 and "Funil do conjunto-ouro" in r.output
    assert not (repo / "tests" / "eval" / "gold-git.yaml").exists()  # dry-run não escreve
    assert runner.invoke(app, ["gold", "build"]).exit_code == 0
    destino = repo / "tests" / "eval" / "gold-git.yaml"
    primeiro = destino.read_bytes()
    assert runner.invoke(app, ["gold", "build"]).exit_code == 0
    assert destino.read_bytes() == primeiro  # byte-idêntico
    texto = primeiro.decode("utf-8")
    assert "autor-secreto" not in texto and "Autor Secreto" not in texto and "Corpo do commit" not in texto
    dados = yaml.safe_load(texto)
    assert dados and all({"query", "relevant_paths", "commit", "kind"} <= set(d) for d in dados)
