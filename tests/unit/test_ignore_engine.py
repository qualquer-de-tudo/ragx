from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ragx.security.ignore_engine import IgnoreEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sub").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".gitignore").write_text("*.log\nbuild/\n", encoding="utf-8")
    (tmp_path / "src" / ".gitignore").write_text("tmp.py\n", encoding="utf-8")
    (tmp_path / ".ragignore").write_text("docs/**\n!docs/keep.md\n", encoding="utf-8")
    return tmp_path


def test_gitignore_basico(repo: Path) -> None:
    e = IgnoreEngine(repo)
    assert e.should_ignore("app.log")[0]
    assert not e.should_ignore("app.py")[0]


def test_gitignore_aninhado_afeta_so_a_subarvore(repo: Path) -> None:
    e = IgnoreEngine(repo)
    assert e.should_ignore("src/tmp.py")[0]
    assert not e.should_ignore("tmp.py")[0], "regra de src/ vazou para a raiz"


def test_negacao_reverte(repo: Path) -> None:
    e = IgnoreEngine(repo)
    assert e.should_ignore("docs/interno.md")[0]
    assert not e.should_ignore("docs/keep.md")[0]


def test_origem_da_decisao_e_reportada(repo: Path) -> None:
    ignored, source = e_source = IgnoreEngine(repo).should_ignore("app.log")
    assert ignored and source and ".gitignore" in source
    assert e_source


def test_defaults_embutidos(repo: Path) -> None:
    e = IgnoreEngine(repo)
    for p in ("node_modules/x.js", ".git/config", "a.min.js", "img.png", "x.sqlite"):
        assert e.should_ignore(p)[0], p


def test_env_nao_e_ignorado_precisa_chegar_ao_scanner(repo: Path) -> None:
    """IgnoreEngine trata de RUÍDO. Quem protege segredo é o scanner."""
    assert not IgnoreEngine(repo).should_ignore(".env")[0]


def _link_dir(link: Path, alvo: Path) -> None:
    """Junction no Windows (é o que o pnpm cria; não exige privilégio), symlink fora."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(alvo), str(link))
    else:
        link.symlink_to(alvo, target_is_directory=True)


def test_pasta_alcancada_por_varios_links_e_visitada_uma_vez(tmp_path: Path) -> None:
    """O node_modules do pnpm é feito de junctions: cada pacote aparece sob o
    caminho de cada dependente. O `rglob` do Python 3.12 entra em junction e
    não lembra onde já esteve. Num monorepo pnpm com worktrees, a busca por
    `.gitignore` passou de 20 minutos a 100% de CPU antes de indexar um
    arquivo (119 s só no node_modules, contra 4 s visitando cada pasta uma vez).
    Aqui, a mesma pasta alcançada por três caminhos tem de contar uma vez."""
    alvo = tmp_path / "store" / "pkg"
    alvo.mkdir(parents=True)
    (alvo / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    for dependente in ("a", "b"):
        (tmp_path / dependente).mkdir()
        _link_dir(tmp_path / dependente / "pkg", alvo)

    nomes = IgnoreEngine(tmp_path, use_defaults=False).source_names
    assert len([n for n in nomes if n.endswith("pkg/.gitignore")]) == 1, nomes


def test_ignore_dentro_de_git_nao_conta_e_os_tres_tipos_sao_achados(tmp_path: Path) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    (tmp_path / ".git" / "info" / ".gitignore").write_text("*\n", encoding="utf-8")
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / ".dockerignore").write_text("x\n", encoding="utf-8")
    (tmp_path / "a" / "b" / ".ragignore").write_text("y\n", encoding="utf-8")
    (tmp_path / "a" / ".gitignore").write_text("z\n", encoding="utf-8")

    nomes = IgnoreEngine(tmp_path, use_defaults=False).source_names
    assert nomes == ["a/.gitignore", ".dockerignore", "a/b/.ragignore"]


# ── poda de pasta ignorada ──────────────────────────────────────────────
def _arvore(tmp_path: Path, gitignore: str) -> Path:
    (tmp_path / ".gitignore").write_text(gitignore, encoding="utf-8")
    for rel in ("src/app.py", "build/x.txt", "build/keep.txt", "node_modules/pkg/.env.example",
                "node_modules/pkg/index.js", "node_modules/keep/a.js", ".env.example"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    return tmp_path


def test_pasta_ignorada_sem_negacao_que_entre_nela_e_podada(tmp_path: Path) -> None:
    e = IgnoreEngine(_arvore(tmp_path, "build/\n!.env.example\n"))
    assert e.can_prune("node_modules")  # default embutido
    assert e.can_prune("build")
    assert not e.can_prune("src")  # não ignorada


def test_negacao_com_caminho_impede_a_poda(tmp_path: Path) -> None:
    e = IgnoreEngine(_arvore(tmp_path, "build/\n!build/keep.txt\n"))
    assert not e.can_prune("build")
    assert not e.should_ignore("build/keep.txt")[0]


def test_include_explicito_so_protege_o_caminho_que_pede(tmp_path: Path) -> None:
    e = IgnoreEngine(_arvore(tmp_path, ""), extra_include=["node_modules/keep/**"])
    assert not e.can_prune("node_modules")
    assert not e.can_prune("node_modules/keep")
    assert e.can_prune("node_modules/pkg")
    # --include genérico é pedido explícito: vale em qualquer lugar
    assert not IgnoreEngine(tmp_path, extra_include=["*.js"]).can_prune("node_modules")


def test_walker_nao_desce_em_pasta_podada_e_mantem_o_resto(tmp_path: Path) -> None:
    from ragx.security.gate import SecurityGate
    from ragx.walk import iter_files

    raiz = _arvore(tmp_path, "build/\n!build/keep.txt\n!.env.example\n")
    vistos = {w.rel_path: w.decision.verdict.value for w in iter_files(raiz, SecurityGate(raiz))}
    assert not any(p.startswith("node_modules/") for p in vistos)  # nem listado como SKIP
    assert vistos["build/keep.txt"] != "skip"  # negação com caminho continua valendo
    assert vistos["build/x.txt"] == "skip"
    assert "src/app.py" in vistos and vistos["src/app.py"] != "skip"
    # a negação genérica vale fora de pasta ignorada, como no git
    assert ".env.example" in vistos


def test_ignore_de_dentro_de_pasta_excluida_nao_e_lido_nem_impede_a_poda(tmp_path: Path) -> None:
    """Worktree do Claude em `.claude/worktrees/`, ignorado, com os `.gitignore`
    do projeto dentro. As negações com caminho deles (`!.yarn/patches`) apontam
    para dentro da pasta excluída e impediam a poda. O git nem lê esses arquivos."""
    (tmp_path / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    wt = tmp_path / ".claude" / "worktrees" / "feature" / "apps" / "admin"
    wt.mkdir(parents=True)
    (wt / ".gitignore").write_text(".yarn/*\n!.yarn/patches\n", encoding="utf-8")

    e = IgnoreEngine(tmp_path)
    assert e.can_prune(".claude/worktrees")
    assert not any("worktrees" in n for n in e.source_names), e.source_names


# ── RAGX-0129: negação com caminho não trava a poda dos irmãos ──────────
def _monorepo(tmp_path: Path) -> Path:
    """Raiz com `!sub/keep/` e `sub/.gitignore` com `!.vscode/extensions.json`:
    o desenho de `src/app` neste repositório (negação do `build`, do `.vscode`)."""
    (tmp_path / ".gitignore").write_text("node_modules/\ndist/\nbuild/\n!sub/build/\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".gitignore").write_text(
        ".vscode/*\n!.vscode/extensions.json\n", encoding="utf-8"
    )
    for rel in ("sub/node_modules/pkg/a.js", "sub/dist/b.js", "sub/build/c.js",
                "sub/.vscode/extensions.json", "sub/.vscode/settings.json", "sub/src/d.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    return tmp_path


def test_negacao_de_um_diretorio_nao_trava_a_poda_dos_irmaos(tmp_path: Path) -> None:
    e = IgnoreEngine(_monorepo(tmp_path))
    # irmãos do alvo da negação: podáveis (antes: False, a poda ficava desligada)
    assert e.can_prune("sub/node_modules")
    assert e.can_prune("sub/dist")
    # o alvo, e o diretório do arquivo reincluído, continuam sendo visitados
    assert not e.can_prune("sub/build")
    assert not e.can_prune("sub/.vscode")
    # e o que estava sendo reincluído continua reincluído
    assert not e.should_ignore("sub/.vscode/extensions.json")[0]
    assert not e.should_ignore("sub/build/c.js")[0]


@pytest.mark.parametrize(
    ("padrao", "escopo", "esperado"),
    [
        (".vscode/extensions.json", "", ".vscode/extensions.json"),
        (".vscode/extensions.json", "src/app", "src/app/.vscode/extensions.json"),
        ("src/app/build/", "", "src/app/build"),
        ("build/**/keep.txt", "", "build"),
        ("node_modules/pkg/**", "", "node_modules/pkg"),
        ("a/*.md", "", "a"),
        ("**/x", "", ""),
        ("!foo", "", ""),
        (".env.example", "", ""),
        ("/a/b.txt", "", "a/b.txt"),
    ],
)
def test_prefixo_literal(padrao: str, escopo: str, esperado: str) -> None:
    from ragx.security.ignore_engine import _prefixo_literal

    # `_prefixo_literal` recebe o padrão SEM o `!` (o chamador já o tirou)
    assert _prefixo_literal(padrao.removeprefix("!"), escopo) == esperado
