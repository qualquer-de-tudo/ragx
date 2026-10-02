"""Escrita que só toca o arquivo quando o CONTEÚDO mudou (RAGX-0148).

`knowledge/` é versionado para ser reidratado: um `sync` sem mudança que reescreve `generated_at` (e o mtime) deixa
arquivos rastreados sujos em todo commit. Aqui o corpo novo é comparado com o que já está no disco; se for igual, o
arquivo não é tocado. `volatile` lista chaves JSON que a comparação ignora (`generated_at`): se SÓ elas mudaram, o
arquivo fica como está; se o conteúdo mudou, o corpo novo (com o `generated_at` novo) é gravado.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _sem_volateis(node: Any, volatile: frozenset[str]) -> Any:
    if isinstance(node, dict):
        return {k: _sem_volateis(v, volatile) for k, v in node.items() if k not in volatile}
    if isinstance(node, list):
        return [_sem_volateis(v, volatile) for v in node]
    return node


def _igual(atual: bytes, novo: bytes, volatile: frozenset[str]) -> bool:
    if atual == novo:
        return True
    if not volatile:
        return False
    try:
        return _sem_volateis(json.loads(atual), volatile) == _sem_volateis(json.loads(novo), volatile)
    except ValueError:  # JSON existente inválido (ou corpo não-JSON): regrava
        return False


def write_bytes_if_changed(path: Path, body: bytes, volatile: Iterable[str] = ()) -> bool:
    """Grava `body` se difere do que está em `path`. Devolve `True` quando gravou."""
    try:
        atual = path.read_bytes() if path.is_file() else None
    except OSError:
        atual = None  # ilegível: regrava
    if atual is not None and _igual(atual, body, frozenset(volatile)):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return True


def write_text_if_changed(path: Path, body: str, volatile: Iterable[str] = ()) -> bool:
    """Como `write_bytes_if_changed`, em UTF-8 com LF (sem tradução de fim de linha, sem BOM)."""
    return write_bytes_if_changed(path, body.encode("utf-8"), volatile)
