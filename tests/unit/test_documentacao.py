"""A documentação acompanha o código — verificado, não prometido.

Duas coisas apodrecem sozinhas em qualquer projeto: comando que existe e não
está documentado, e link que aponta para um arquivo renomeado. Nenhuma das
duas quebra um teste funcional, e as duas corroem a confiança em tudo que está
escrito.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ragx.cli.main import app

RAIZ = Path(__file__).resolve().parents[2]
DOCS = RAIZ / "docs"
CLI_DOC = DOCS / "14-cli.md"

# `[texto](alvo)` com alvo relativo — ignora http(s), mailto e âncora pura.
_LINK = re.compile(r"\[[^\]]*\]\((?!https?://|mailto:|#)([^)]+)\)")


def _comandos() -> set[str]:
    """Todo comando invocável, incluindo subcomando de grupo."""
    out: set[str] = set()

    def anda(typer_app, prefixo: str = "") -> None:
        for cmd in typer_app.registered_commands:
            nome = cmd.name or (cmd.callback.__name__ if cmd.callback else "")
            if nome:
                out.add(f"{prefixo}{nome}".replace("_", "-"))
        for grupo in typer_app.registered_groups:
            nome = grupo.name or ""
            if nome and grupo.typer_instance is not None:
                out.add(nome)
                anda(grupo.typer_instance, f"{nome} ")

    anda(app)
    return out


def test_todo_comando_da_cli_esta_documentado() -> None:
    texto = CLI_DOC.read_text(encoding="utf-8")
    faltando = sorted(c for c in _comandos() if f"ragx {c}" not in texto)
    assert not faltando, (
        f"comandos ausentes de docs/14-cli.md: {faltando}. "
        f"Comando sem documentação é comando que ninguém usa."
    )


def test_a_cli_nao_documenta_comando_inexistente() -> None:
    """O inverso: documentação que promete o que a CLI não entrega."""
    texto = CLI_DOC.read_text(encoding="utf-8")
    reais = _comandos()
    grupos = {c for c in reais if " " not in c}
    citados = {
        m.group(1).strip()
        for m in re.finditer(r"^\s*ragx ([a-z][a-z-]*(?: [a-z][a-z-]*)?)", texto, re.M)
    }
    fantasmas = sorted(
        c for c in citados
        if c not in reais and c.split()[0] not in grupos and not c.startswith("--")
    )
    assert not fantasmas, f"docs/14-cli.md cita comandos que não existem: {fantasmas}"


@pytest.mark.parametrize(
    "arquivo",
    [
        *sorted(
            p for base in ("docs", "task")
            for p in (RAIZ / base).rglob("*.md")
        ),
        RAIZ / "README.md",
    ],
    ids=lambda p: str(p.relative_to(RAIZ)).replace("\\", "/"),
)
def test_links_relativos_apontam_para_arquivo_existente(arquivo: Path) -> None:
    quebrados = []
    for alvo in _LINK.findall(arquivo.read_text(encoding="utf-8")):
        limpo = alvo.split("#", 1)[0].strip()
        if not limpo:
            continue  # link só com âncora
        destino = (arquivo.parent / limpo).resolve()
        if not destino.exists():
            quebrados.append(alvo)
    assert not quebrados, f"links quebrados em {arquivo.name}: {quebrados}"


# ── instalação ──────────────────────────────────────────────────────────
def test_extra_all_cobre_o_que_o_ragx_promete() -> None:
    """Instalar e o `ragx mcp serve` falhar é a pior surpresa possível.

    Aconteceu de verdade: o instalador usava o extra `embed`, o pacote `mcp`
    ficava de fora, e `ragx mcp tools` morria com `ModuleNotFoundError` depois
    de uma instalação que se declarou bem-sucedida.
    """
    import tomllib

    dados = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    extras = dados["project"]["optional-dependencies"]
    assert "all" in extras, "o extra `all` é o conjunto recomendado"

    pacotes = " ".join(extras["all"])
    for obrigatorio in ("mcp", "fastembed"):
        assert obrigatorio in pacotes, (
            f"`all` precisa de {obrigatorio}: servir agentes por MCP e busca "
            f"semântica são o propósito do RAGX, não acessórios"
        )


@pytest.mark.parametrize("script", ["install/install.sh", "install/install.ps1"])
def test_instalador_poe_o_comando_no_path(script: str) -> None:
    """O sintoma clássico é «instalei e o comando não existe».

    `uv tool` instala em um diretório que nem Linux nem Windows têm no PATH por
    padrão. O instalador precisa gravar isso no perfil — e dizer que só vale na
    próxima sessão.
    """
    texto = (RAIZ / script).read_text(encoding="utf-8-sig")
    assert "PATH" in texto
    # Fixar o interpretador: sem isso o uv pode pegar um Python 3.10 e o RAGX,
    # que usa StrEnum, quebra com um ImportError longe da causa.
    assert "--python" in texto, "o instalador precisa fixar a versão do Python"
    # Verificar em vez de prometer.
    assert "doctor" in texto, "o instalador precisa verificar o que instalou"


@pytest.mark.parametrize("script", ["install/install.sh", "install/install.ps1"])
def test_instalador_registra_o_mcp(script: str) -> None:
    texto = (RAIZ / script).read_text(encoding="utf-8-sig")
    assert "mcpServers" in texto
    assert "mcp" in texto and "serve" in texto


def test_instalador_windows_tem_bom() -> None:
    """O PowerShell 5.1 ainda é o padrão do Windows e lê `.ps1` sem BOM como
    ANSI — todo acento vira mojibake na tela do instalador."""
    assert (RAIZ / "install/install.ps1").read_bytes()[:3] == b"\xef\xbb\xbf"
