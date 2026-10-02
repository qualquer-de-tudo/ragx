"""Testes arquiteturais.

Verificam invariantes de design que nenhum teste funcional pega — e que
revisão de código esquece. Ver docs/13-testes-hardening.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

SRC = Path(__file__).resolve().parents[2] / "src" / "ragx"

# Módulos que dariam ao MCP capacidade de ler o filesystem, executar processo
# ou falar com a rede. Ver ADR-0006.
FORBIDDEN_IN_MCP = {
    "os", "subprocess", "pathlib", "shutil", "socket", "requests", "httpx",
    "urllib", "urllib.request", "glob", "tempfile", "io",
}
FORBIDDEN_CALLS_IN_MCP = {"open", "exec", "eval", "compile", "__import__"}

# Só estes dois podem ler o filesystem do projeto-alvo.
FILESYSTEM_READERS = {"ragx.walk", "ragx.sync.incremental"}
_READ_CALLS = {"read_bytes", "read_text", "iterdir", "rglob", "glob", "walk", "scandir"}


def _modules(package: Path) -> list[Path]:
    return [p for p in package.rglob("*.py") if "__pycache__" not in p.parts]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
            found.add(node.module)
    return found


def _called_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                out.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                out.add(fn.attr)
    return out


# ── ADR-0006: MCP é casca fina ──────────────────────────────────────────
def test_mcp_nao_importa_filesystem_nem_rede() -> None:
    for path in _modules(SRC / "mcp"):
        proibidos = _imports(path) & FORBIDDEN_IN_MCP
        assert not proibidos, (
            f"{path.name} importa {sorted(proibidos)} — o MCP não pode ler o "
            f"filesystem nem falar com a rede (ADR-0006)"
        )


def test_mcp_nao_chama_open_nem_exec() -> None:
    """Proibição direta de `open` no pacote MCP.

    É um teste rombudo de propósito: ele já barrou uma tentativa legítima
    (gravar log de erro) e forçou a capacidade para `ragx.diagnostics`, um
    módulo separado e auditável. Rombudo e barato vale mais que sutil e frágil.
    """
    for path in _modules(SRC / "mcp"):
        proibidos = _called_names(path) & FORBIDDEN_CALLS_IN_MCP
        assert not proibidos, f"{path.name} chama {sorted(proibidos)}"


def test_mcp_abre_o_banco_somente_leitura() -> None:
    """Indexar é operação de CLI, não de agente."""
    fonte = (SRC / "mcp" / "server.py").read_text(encoding="utf-8")
    assert "open_db(" in fonte
    for linha in fonte.splitlines():
        if "open_db(" in linha and "read_only" not in linha:
            pytest.fail(f"abertura sem read_only: {linha.strip()}")


# ── ADR-0008: só dois módulos leem o projeto-alvo ───────────────────────
def test_apenas_modulos_autorizados_leem_o_filesystem() -> None:
    infratores: list[str] = []
    for path in _modules(SRC):
        rel = path.relative_to(SRC.parent)
        module = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        # A CLI, config, storage e builders leem artefatos PRÓPRIOS do RAGX
        # (ragx.toml, knowledge/, .ragx/), não o código-fonte do projeto-alvo.
        if module in FILESYSTEM_READERS or any(
            module.startswith(p)
            # Estes leem artefatos PRÓPRIOS do RAGX (ragx.toml, knowledge/,
            # .ragx/, agents/<nome>/), nunca o código-fonte do projeto-alvo.
            for p in ("ragx.cli", "ragx.config", "ragx.storage", "ragx.security",
                      "ragx.dictionary", "ragx.portability", "ragx.embeddings",
                      "ragx.context", "ragx.graph", "ragx.sizing", "ragx.indexing",
                      "ragx.federation", "ragx.sync", "ragx.tokens", "ragx.search",
                      "ragx.agents", "ragx.base", "ragx.tasks", "ragx.githooks",
                      "ragx.perf", "ragx.hooklight", "ragx.worktrees")
            # `ragx.perf` lê só os transcripts do próprio Claude Code
            # (`~/.claude/projects/`) e o `.ragx/logs/mcp.jsonl`: nunca o
            # código do projeto-alvo. De cada transcript sai um número (tempo);
            # o conteúdo das mensagens não é retido nem impresso.
            # `ragx.githooks` só lê e escreve os arquivos de hook dentro de
            # `gitinfo.hooks_dir(root)` (`.git/hooks/` ou o que `core.hooksPath`
            # apontar) -- nunca um caminho arbitrário do projeto. Mesmo esses
            # arquivos, o conteúdo lido só é reescrito no lugar ou reduzido a
            # um booleano (`installed()`); nunca chega ao índice, ao MCP, a
            # log nem a stdout.
            # `ragx.worktrees` (RAGX-0170) só lista `.ragx/cache/emb/*.sqlite` e abre `.ragx/knowledge.db`
            # dos worktrees, em leitura: nunca o código do projeto.
            # `ragx.hooklight` (RAGX-0143) lê só artefatos PRÓPRIOS: `ragx.toml`,
            # `.ragx/status.json` e o `registry.json` do hub, com `read_text`. Um
            # teste abaixo proíbe nele `read_bytes` e qualquer varredura de pasta.
        ):
            continue
        if _called_names(path) & _READ_CALLS:
            infratores.append(module)
    assert not infratores, f"leitura de filesystem fora dos módulos autorizados: {infratores}"


def test_orquestracao_nao_le_o_codigo_do_projeto() -> None:
    """`ragx.tasks` lê artefatos PRÓPRIOS; o código do projeto vem do índice.

    Um planner que varresse `docs/` ou `src/` para montar contexto viraria um
    terceiro leitor de filesystem — e o valor do ADR-0008 é justamente que
    essa lista não cresça sem alguém decidir. Este teste já pegou um `glob`
    em `docs/adr/` que foi trocado por uma consulta ao índice.
    """
    # `rglob`, `walk` e `scandir` VARREM uma árvore — é assim que um módulo
    # vira leitor do projeto sem ninguém notar. `read_bytes` ingere conteúdo.
    # `iterdir` sobre uma pasta conhecida de artefato é outra coisa, e é o que
    # a poda de `knowledge/tasks/` precisa.
    proibidos = {"read_bytes", "rglob", "walk", "scandir"}
    for path in _modules(SRC / "tasks"):
        achados = _called_names(path) & proibidos
        assert not achados, (
            f"ragx.tasks.{path.stem} varre o filesystem ({sorted(achados)}) — "
            f"o conhecimento do projeto vem do índice"
        )

    # `glob` e `iterdir` só sobre os artefatos do próprio RAGX.
    for path in _modules(SRC / "tasks"):
        fonte = path.read_text(encoding="utf-8")
        for linha in fonte.splitlines():
            if ".glob(" not in linha and ".iterdir(" not in linha:
                continue
            assert any(
                marca in linha
                for marca in ("MIGRATIONS_DIR", "alvo /", "*.json", "*.sql",
                              "folder.iterdir")
            ), f"varredura fora dos artefatos do RAGX em {path.name}: {linha.strip()}"


def test_base_gerencia_fontes_mas_nao_le_conteudo() -> None:
    """Conhecimento base é conteúdo de TERCEIRO — a superfície mais perigosa.

    `ragx.base` clona, registra e conta arquivos; ele nunca lê os bytes. Quem lê
    é `iter_files`, e ali o SecurityGate roda igual ao do projeto. Se alguém
    algum dia tentar um atalho ("é só um README, lê direto"), este teste quebra.
    """
    for path in _modules(SRC / "base"):
        proibidos = _called_names(path) & {"read_bytes", "open"}
        assert not proibidos, (
            f"ragx.base.{path.stem} lê conteúdo direto ({sorted(proibidos)}) — "
            f"conteúdo de terceiro entra por iter_files, passando pelo gate"
        )


def test_conhecimento_base_fica_fora_do_git() -> None:
    """`knowledge/` é versionado e tem orçamento; base não cabe nele.

    Base não é reidratável (não existe no working tree) e duplicá-la em cada
    repositório queimaria o orçamento à toa. Vai o registro, não o conteúdo.
    """
    fonte = (SRC / "sync" / "serialize.py").read_text(encoding="utf-8")
    for consulta in ("FROM documents WHERE", "FROM embeddings e", "FROM entities e"):
        assert consulta in fonte, f"consulta sumiu: {consulta}"
    assert fonte.count("base_source.PREFIX") >= 4, (
        "alguma consulta de serialização deixou de excluir @base/"
    )


def test_walker_passa_pelo_gate_antes_de_entregar_bytes() -> None:
    """Nenhum caminho do walker devolve conteúdo sem um GateDecision.

    Desde a RAGX-0152 a leitura tem dois estágios: `_decidir`/`iter_candidates` fazem só as decisões
    BARATAS (sem abrir o arquivo) e `read_candidate` é o UNICO lugar que lê bytes e chama `gate.admit`,
    no processo principal ou no worker do pipeline paralelo. Os pontos de entrada (`iter_files`,
    `iter_paths`, `_examinar`) só compõem os dois estágios. O helper `_walk` fica de fora de propósito:
    só enumera caminhos, nunca entrega bytes.
    """
    fonte = (SRC / "walk.py").read_text(encoding="utf-8")
    assert "gate.admit(" in fonte, "walker precisa chamar o gate"

    tree = ast.parse(fonte)
    funcoes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for nome in ("iter_files", "iter_paths", "iter_candidates", "_examinar", "_decidir", "read_candidate"):
        assert nome in funcoes, f"{nome} sumiu"

    # ler bytes e admitir no gate: SÓ em `read_candidate`
    def _usa(no: ast.AST, nome: str) -> bool:
        return any(
            (isinstance(n, ast.Attribute) and n.attr == nome) or (isinstance(n, ast.Name) and n.id == nome)
            for n in ast.walk(no)
        )

    assert [n for n, f in funcoes.items() if _usa(f, "read_bytes")] == ["read_candidate"]
    assert [n for n, f in funcoes.items() if _usa(f, "admit")] == ["read_candidate"]

    # todo retorno de `read_candidate` é `None` (sumiu) ou um WalkedFile com decisão
    retornos = [n for n in ast.walk(funcoes["read_candidate"]) if isinstance(n, ast.Return)]
    assert retornos
    for node in retornos:
        trecho = ast.dump(node)
        assert "WalkedFile" in trecho or "Constant(value=None)" in trecho, f"retorno sem decisão: {trecho[:140]}"
    # e o conteúdo só entra no WalkedFile pela `decision` que veio de `gate.admit`
    assert any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "admit"
        for n in ast.walk(funcoes["read_candidate"])
    )

    # os estágios de decisão barata não leem nem admitem; os pontos de entrada compõem os estágios
    for nome in ("iter_files", "iter_paths", "iter_candidates", "_decidir"):
        texto = ast.dump(funcoes[nome])
        assert "read_bytes" not in texto and "'admit'" not in texto, f"{nome} lê ou admite por fora"
    assert "read_candidate" in ast.dump(funcoes["iter_files"]) and "iter_candidates" in ast.dump(funcoes["iter_files"])
    assert "_examinar" in ast.dump(funcoes["iter_paths"]), "iter_paths precisa delegar a _examinar"
    assert "_decidir" in ast.dump(funcoes["_examinar"]) and "read_candidate" in ast.dump(funcoes["_examinar"])
    for nome in ("iter_paths", "iter_candidates"):
        assert not [n for n in ast.walk(funcoes[nome]) if isinstance(n, ast.Yield) and "WalkedFile" in ast.dump(n)], (
            f"{nome} fabrica WalkedFile por conta própria"
        )


def test_pipeline_paralelo_so_le_arquivo_por_read_candidate() -> None:
    """`ragx.indexing.parallel` (RAGX-0152) roda o Gate COMPLETO no worker e nunca abre arquivo por conta própria."""
    caminho = SRC / "indexing" / "parallel.py"
    fonte = caminho.read_text(encoding="utf-8")
    tree = ast.parse(fonte)
    assert "read_candidate" in fonte and "SecurityGate(" in fonte
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            nome = getattr(n.func, "attr", None) or getattr(n.func, "id", "")
            assert nome not in {"read_bytes", "read_text", "open", "scandir", "listdir"}, (
                f"parallel.py lê o filesystem por fora de read_candidate: {nome}"
            )
    # não importa a configuração nem a CLI: cada worker em `spawn` pagaria o pydantic/typer
    importados = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert not any(m == "ragx.config" or m.startswith(("ragx.cli", "typer")) for m in importados), sorted(importados)


# ── domínio não conhece infraestrutura ──────────────────────────────────
def test_core_nao_importa_infraestrutura() -> None:
    infra = {"sqlite3", "numpy", "yaml", "typer", "rich", "requests", "httpx", "mcp"}
    for path in _modules(SRC / "core"):
        vazou = _imports(path) & infra
        assert not vazou, f"ragx.core.{path.stem} importa infraestrutura: {sorted(vazou)}"


def test_security_nao_depende_de_camadas_superiores() -> None:
    superiores = {"ragx.search", "ragx.graph", "ragx.context", "ragx.mcp", "ragx.cli"}
    for path in _modules(SRC / "security"):
        vazou = {m for m in _imports(path) if m in superiores}
        assert not vazou, f"ragx.security.{path.stem} depende de {sorted(vazou)}"


# ── regras de segurança são declarativas ────────────────────────────────
def test_regras_ficam_em_yaml_e_nao_em_python() -> None:
    """Auditável por alguém de segurança sem ler Python."""
    rules = SRC / "security" / "rules"
    assert (rules / "patterns.yaml").is_file()
    assert (rules / "filenames.yaml").is_file()
    scanner = (SRC / "security" / "scanner.py").read_text(encoding="utf-8")
    # os únicos regex embutidos no scanner são utilitários, não regras
    assert scanner.count("re.compile") <= 2, "regra de detecção embutida em código"


def test_hooklight_nao_le_bytes_nem_varre_pasta() -> None:
    """A entrada leve dos hooks lê só texto de artefatos próprios e nunca percorre diretório."""
    path = SRC / "hooklight.py"
    proibidos = _called_names(path) & {"read_bytes", "rglob", "walk", "scandir", "iterdir", "glob"}
    assert not proibidos, f"ragx.hooklight chama {sorted(proibidos)}"
