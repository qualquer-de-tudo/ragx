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


def test_instalador_windows_e_ascii_sem_bom() -> None:
    """O `.ps1` precisa sobreviver a `irm | iex`.

    Esta regra substituiu a anterior, que exigia BOM. O BOM resolvia a leitura
    do arquivo em DISCO pelo PowerShell 5.1, mas quebrava o caminho que importa
    mais: o `Invoke-RestMethod` não recebe charset num asset de release
    (`application/octet-stream`), decodifica o corpo como Latin-1, e o script
    chega corrompido — o parser cospe dezenas de "Token inesperado".

    ASCII puro resolve os dois de uma vez. Verificado servindo o script por
    HTTP: com acentos o `irm | iex` falha; em ASCII, instala.
    """
    bruto = (RAIZ / "install/install.ps1").read_bytes()
    assert bruto[:3] != b"\xef\xbb\xbf", "BOM quebra `irm | iex`"

    fora = sorted({b for b in bruto if b > 127})
    assert not fora, (
        f"bytes não-ASCII no instalador: {fora[:8]} — o `irm` do PowerShell 5.1 "
        f"os decodifica como Latin-1 e o script não parseia"
    )


@pytest.mark.parametrize("script", ["install/install.sh", "install/install.ps1"])
def test_instalador_encontra_o_wheel_baixado(script: str) -> None:
    """Com repositório privado, o download é o ÚNICO caminho sem credencial.

    A pessoa baixa os arquivos da release para uma pasta e roda o instalador
    ali. Fazê-la digitar o caminho do `.whl` é um passo a mais para errar — e
    procurar o clone antes do wheel inverteria a probabilidade do caso real.
    """
    texto = (RAIZ / script).read_text(encoding="utf-8")
    if script.endswith(".ps1"):
        assert "Encontrar-Wheel" in texto
        assert "Instalar-Extensao" in texto
        # O código de saída precisa ser 0 no sucesso: o `ragx doctor` sai
        # diferente de zero enquanto não há índice, e isso vazava.
        assert "$global:LASTEXITCODE = 0" in texto
    else:
        assert "encontrar_wheel" in texto
        assert "instalar_extensao" in texto
    assert "ragx-*.whl" in texto


@pytest.mark.parametrize("script", ["install/install.sh", "install/install.ps1"])
def test_instalador_sobrevive_a_execucao_por_pipe(script: str) -> None:
    """`curl | bash` e `irm | iex` não têm arquivo em disco.

    Nesse modo `${BASH_SOURCE[0]}` e `$PSScriptRoot` vêm VAZIOS. A versão
    anterior fazia `Split-Path -Parent ''` e morria logo depois de instalar o
    `uv`, com uma mensagem sem nenhuma relação com a causa.
    """
    texto = (RAIZ / script).read_text(encoding="utf-8")
    if script.endswith(".ps1"):
        # Detecta a ausência do arquivo ANTES de usar o caminho.
        assert "Obter-RaizLocal" in texto
        assert "if (-not $arquivo) { return '' }" in texto
        # `exit` fecharia o terminal de quem rodou por `iex`.
        assert "exit 1" not in texto, "use `throw`: `exit` mata a sessão de quem rodou"
    else:
        assert "BASH_SOURCE[0]:-" in texto
        assert '-f "${BASH_SOURCE[0]}"' in texto
