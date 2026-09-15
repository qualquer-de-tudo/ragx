"""O plugin do VS Code chama a CLI. Esta é a única checagem que os une.

O transporte de reserva do plugin monta linhas de comando como texto:
`['documents', '--path', x]`. Nada no TypeScript sabe se essa flag existe, e
nada no Python sabe que alguém a escreveu. O resultado, quando diverge, é o
pior tipo de falha: o `execFile` devolve erro, o plugin mostra "não indexado",
e a suspeita cai sobre o Security Gate — que não fez nada.

Aconteceu duas vezes neste repositório: `--filter`, que nunca existiu, e
`chunks <caminho>` posicional, quando a CLI quer `--document`.

O par deste teste está em `vscode-plugin/tests/unit/client.test.ts`, que fixa
o argv que o cliente produz. Os dois juntos fecham o ciclo: um garante o que o
plugin manda, o outro garante que a CLI aceita.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest
import typer

from ragx.cli.main import app

RAIZ = Path(__file__).resolve().parents[2]
CLIENTE = RAIZ / "vscode-plugin" / "src" / "rag" / "CliClient.ts"

#: Flags que o Typer dá de graça a todo comando.
_GLOBAIS = {"--help"}

#: Quebra o arquivo em métodos: `  async nome(` ou `  nome(`.
_METODO = re.compile(r"^  (?:async )?(\w+)[(<]", re.M)
#: Só arrays que viram linha de comando: o argumento de `exec` e a variável
#: `args` que ele recebe. Qualquer array de strings serviria — e a lista de
#: arquivos de ignore dentro de `security()` viraria um "comando inexistente".
_LINHA_DE_COMANDO = re.compile(
    r"(?:exec<[^>]*>\(\s*|const args(?:\s*:\s*string\[\])?\s*=\s*)\[(.*?)\]",
    re.S,
)
_STRINGS = re.compile(r"'([^']*)'")
_FLAG = re.compile(r"'(--[a-z][a-z-]*)'")


def _arvore() -> dict[tuple[str, ...], set[str]]:
    """Comandos reais da CLI e as opções que cada um aceita."""
    raiz = typer.main.get_command(app)
    out: dict[tuple[str, ...], set[str]] = {}

    def anda(grupo, prefixo: tuple[str, ...]) -> None:
        for nome, cmd in getattr(grupo, "commands", {}).items():
            caminho = (*prefixo, nome)
            opcoes = {
                s for p in cmd.params for s in getattr(p, "opts", []) if s.startswith("--")
            }
            out[caminho] = opcoes | _GLOBAIS
            anda(cmd, caminho)

    anda(raiz, ())
    return out


def _chamadas() -> dict[str, tuple[list[tuple[str, ...]], set[str]]]:
    """Por método do cliente: os comandos invocados e as flags usadas."""
    texto = CLIENTE.read_text(encoding="utf-8")
    limites = [(m.group(1), m.start()) for m in _METODO.finditer(texto)]
    limites.append(("<fim>", len(texto)))

    out: dict[str, tuple[list[tuple[str, ...]], set[str]]] = {}
    for (nome, inicio), (_, fim) in pairwise(limites):
        corpo = texto[inicio:fim]
        comandos: list[tuple[str, ...]] = []
        for m in _LINHA_DE_COMANDO.finditer(corpo):
            itens = _STRINGS.findall(m.group(1))
            # O comando são os literais ANTES da primeira flag. O que vem
            # depois é argumento, e argumento é valor, não nome de comando.
            caminho: list[str] = []
            for item in itens:
                if item.startswith("-"):
                    break
                caminho.append(item)
            if caminho:
                comandos.append(tuple(caminho))
        flags = set(_FLAG.findall(corpo))
        if comandos or flags:
            out[nome] = (comandos, flags)
    return out


@pytest.mark.skipif(not CLIENTE.is_file(), reason="plugin do VS Code ausente")
def test_todo_comando_que_o_plugin_chama_existe_na_cli() -> None:
    arvore = _arvore()
    desconhecidos: list[str] = []

    for metodo, (comandos, _) in _chamadas().items():
        for caminho in comandos:
            # Um caminho pode ser `('task', 'show', 'T-1')`: o terceiro item é
            # argumento. Aceita o prefixo mais longo que é comando de verdade.
            if any(caminho[:n] in arvore for n in range(len(caminho), 0, -1)):
                continue
            desconhecidos.append(f"{metodo}: ragx {' '.join(caminho)}")

    assert not desconhecidos, (
        "o plugin chama comandos que a CLI não tem: "
        f"{desconhecidos}. Isso vira erro de execução com mensagem enganosa."
    )


@pytest.mark.skipif(not CLIENTE.is_file(), reason="plugin do VS Code ausente")
def test_toda_flag_que_o_plugin_usa_existe_no_comando_que_a_recebe() -> None:
    arvore = _arvore()
    invalidas: list[str] = []

    for metodo, (comandos, flags) in _chamadas().items():
        if not flags:
            continue
        aceitas: set[str] = set()
        for caminho in comandos:
            for n in range(len(caminho), 0, -1):
                if caminho[:n] in arvore:
                    aceitas |= arvore[caminho[:n]]
                    break
        for flag in sorted(flags - aceitas):
            invalidas.append(f"{metodo}: {flag} (comandos: {[' '.join(c) for c in comandos]})")

    assert not invalidas, (
        f"flags que nenhum comando invocado aceita: {invalidas}. "
        f"O Typer recusa, o plugin mostra um erro que não aponta para a causa."
    )


@pytest.mark.skipif(not CLIENTE.is_file(), reason="plugin do VS Code ausente")
def test_o_plugin_sempre_pede_json() -> None:
    """Saída humana muda de forma sem aviso; `--json` é contrato.

    A exceção é `watch --once --plain`, que já imprime JSON por outro caminho.
    """
    texto = CLIENTE.read_text(encoding="utf-8")
    for metodo, (comandos, flags) in _chamadas().items():
        if not comandos or metodo in ("exec", "log"):
            continue
        # `--format json` no `context`, `--plain` no `watch`: os dois comandos
        # escolhem o formato por outra flag. O resto usa `--json`.
        assert flags & {"--json", "--plain", "--format"}, (
            f"{metodo} lê a saída humana do RAGX: {[' '.join(c) for c in comandos]}"
        )
    # E nenhuma saída humana é interpretada em lugar nenhum.
    assert "stdout.split" not in texto
