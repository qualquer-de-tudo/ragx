"""O que já foi entregue nesta sessão, para não reenviar o mesmo chunk inteiro (RAGX-0159).

Numa sessão, o agente refaz perguntas parecidas e o `build_context` reenviava os mesmos chunks. O
`dedup` do engine só limpa a repetição DENTRO de um pack; este livro-razão cuida da repetição ENTRE
packs: um chunk já entregue volta como referência (`caminho:linhas [id]`), e `get_chunk` o reabre.

Em memória, um por processo (o servidor MCP sobe um por sessão do cliente). Guarda só o id do chunk, o
caminho, as linhas, os tokens e quando foi entregue: **nunca o conteúdo**. Limitações conhecidas, e por
isso o TTL é curto: o servidor não sabe quando o cliente compactou o contexto ou deu `/clear`, e não
distingue o agente principal de um subagente (que compartilha o servidor, mas não o contexto).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Delivered:
    chunk_id: str
    document_path: str
    start_line: int
    end_line: int
    tokens: int
    at: float


class SessionLedger:
    def __init__(
        self,
        ttl_s: float = 45 * 60,
        max_entries: int = 2000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl_s = ttl_s
        self.max_entries = max(max_entries, 1)
        self._clock = clock
        self._entries: OrderedDict[str, Delivered] = OrderedDict()
        self._lock = threading.Lock()

    def mark(self, chunk_id: str, document_path: str, start_line: int, end_line: int, tokens: int) -> None:
        if not chunk_id:
            return
        with self._lock:
            self._entries.pop(chunk_id, None)  # reentra no fim: o mais recente é o último a ser despejado
            self._entries[chunk_id] = Delivered(
                chunk_id, document_path, start_line, end_line, tokens, self._clock()
            )
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def seen(self, chunk_id: str) -> Delivered | None:
        """A entrega, se ainda vale (dentro do TTL). Vencida, some do livro-razão."""
        with self._lock:
            entry = self._entries.get(chunk_id)
            if entry is None:
                return None
            if self._clock() - entry.at > self.ttl_s:
                del self._entries[chunk_id]
                return None
            return entry

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def from_config(cfg: Any) -> SessionLedger | None:
    """O livro-razão da configuração, ou `None` com `[context] session_dedupe = false`."""
    c = cfg.context
    if not c.session_dedupe:
        return None
    return SessionLedger(ttl_s=c.session_ttl_minutes * 60, max_entries=c.session_max_chunks)
