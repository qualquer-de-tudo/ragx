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
