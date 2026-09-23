"""Registro de diagnóstico em `.ragx/logs/`.

Vive fora de `ragx.mcp` de propósito. A invariante do ADR-0006 é que o servidor
MCP não fale com o filesystem; o teste arquitetural verifica isso proibindo
`open` naquele pacote. Um gravador de log é uma capacidade separada e auditável
— e fica aqui, num módulo que faz só isso e nada mais.

Nada do que passa por aqui vai para o agente: o que ele recebe é um código de
erro e uma mensagem genérica.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from ragx.storage.db import utcnow

MAX_BYTES = 2 * 1024 * 1024


def log_exception(state_dir: Path, scope: str, exc: BaseException) -> None:
    """Grava o traceback completo. Falha de log nunca vira falha adicional."""
    try:
        folder = Path(state_dir) / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "errors.log"
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"--- {utcnow()} {scope}: {type(exc).__name__}\n")
            fh.write("".join(traceback.format_exception(exc)))
            fh.write("\n")
    except Exception:
        pass


def log_mcp_call(state_dir: Path, entry: dict[str, Any]) -> None:
    """Grava telemetria de chamada MCP. Falha de log nunca vira falha adicional."""
    try:
        folder = Path(state_dir) / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "mcp.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_path(state_dir: Path) -> Path:
    return Path(state_dir) / "logs" / "errors.log"
