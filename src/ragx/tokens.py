"""Contagem de tokens.

Abstração (`TokenCounter`) com implementação padrão heurística e sem dependência
nativa. `tiktoken` entra como upgrade opcional: mesma interface, mais precisão.

A contagem é declaradamente ESTIMATIVA — o ContextPack sempre reporta
`estimated_tokens` e garante `estimated_tokens <= budget` com margem.
"""

from __future__ import annotations

import re
from typing import Protocol

_TOKENISH = re.compile(r"\w+|[^\w\s]")


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class HeuristicCounter:
    """Aproxima BPE sem baixar modelo: palavras longas custam mais de 1 token.

    Erro medido contra cl100k_base fica em torno de 10% para código e prosa —
    suficiente para orçamento, que já trabalha com margem.
    """

    name = "heuristic"

    def count(self, text: str) -> int:
        if not text:
            return 0
        total = 0
        for piece in _TOKENISH.findall(text):
            total += 1 if len(piece) <= 4 else (len(piece) + 3) // 4
        return total


class TiktokenCounter:
    """Usa tiktoken quando instalado (`pip install ragx[tokens]`)."""

    name = "tiktoken:cl100k_base"

    def __init__(self) -> None:
        import tiktoken

        self._enc = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._enc.encode(text, disallowed_special=()))


def get_counter(prefer: str = "auto") -> TokenCounter:
    if prefer in ("auto", "tiktoken"):
        try:
            return TiktokenCounter()
        except Exception:
            if prefer == "tiktoken":
                raise
    return HeuristicCounter()


_default: TokenCounter | None = None


def count_tokens(text: str) -> int:
    global _default
    if _default is None:
        _default = get_counter()
    return _default.count(text)
