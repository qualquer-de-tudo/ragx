"""Texto do contexto em markdown, em funções puras.

Fica separado de `render.py` de propósito: o `budget` (que decide quantos
fragmentos cabem) e o `engine` (que mede o que saiu) precisam contar EXATAMENTE
o mesmo texto que o agente vai receber, e `render.py` importa o `engine`.
Nenhuma função daqui conhece `ContextPack`.

Antes, o orçamento assumia 12 tokens de cabeçalho por fragmento e
`estimated_tokens` somava só o conteúdo: o cabeçalho real (`## [i] caminho:linhas
› nome`) custa ~33, e um pedido de 3.000 tokens chegava a 7.983 no fio (RAGX-0154).
"""

from __future__ import annotations

from collections.abc import Sequence

from ragx.tokens import count_tokens


def label(path: str, start_line: int, end_line: int, name: str | None) -> str:
    loc = f"{path}:{start_line}-{end_line}"
    return f"{loc} › {name}" if name else loc


def header(index: int, path: str, start_line: int, end_line: int, name: str | None,
           compressed: bool = False) -> str:
    marca = "  (comprimido)" if compressed else ""
    return f"## [{index}] {label(path, start_line, end_line, name)}{marca}"


def footer(n_sources: int, estimated_tokens: int, budget: int, n_dropped: int) -> str:
    extra = f" · {n_dropped} candidatos descartados" if n_dropped else ""
    return f"{n_sources} fonte(s) · ~{estimated_tokens} / {budget} tokens{extra}"


def markdown(
    parts: Sequence[tuple[str, str]],
    n_sources: int,
    estimated_tokens: int,
    budget: int,
    n_dropped: int,
    title: str | None = None,
) -> str:
    """`parts` é uma lista de `(cabeçalho, conteúdo)`; `title` só a CLI usa."""
    lines: list[str] = [f"# Contexto — {title}", ""] if title is not None else []
    for head, content in parts:
        lines.extend([head, "", content, ""])
    lines.append("---")
    lines.append(footer(n_sources, estimated_tokens, budget, n_dropped))
    return "\n".join(lines)


def header_cost(path: str, start_line: int, end_line: int, name: str | None) -> int:
    """Tokens do cabeçalho de UM fragmento, com o índice no pior caso (dois dígitos)
    e as quebras de linha que o cercam."""
    return count_tokens(header(10, path, start_line, end_line, name) + "\n\n\n")


def footer_cost(budget: int) -> int:
    """Tokens do rodapé no pior caso: números grandes e o aviso de descartados."""
    return count_tokens("\n---\n" + footer(99, budget, budget, 999))
