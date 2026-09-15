"""Pacote da CLI.

A reconfiguração de encoding vive aqui porque precisa acontecer ANTES de
qualquer `rich.Console` ser construído nos módulos de comando — e importar
`ragx.cli.commands.*` passa necessariamente por este __init__.
"""

from __future__ import annotations

import contextlib
import sys


def _force_utf8() -> None:
    """O console do Windows costuma vir em cp1252, que não codifica '✓', '→' nem
    caixa de desenho — e aí a CLI morre com UnicodeEncodeError no meio de um
    relatório. Um ponto de correção resolve para todos os comandos.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")


_force_utf8()
