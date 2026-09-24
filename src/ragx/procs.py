"""Processos filhos que nunca abrem janela de terminal.

No Windows, um programa de console lançado por um processo SEM console ganha uma
janela nova. É o caso do `git` chamado pela indexação que o hook de commit dispara
destacada: cada `git rev-parse` piscava um terminal na cara de quem só commitou.

`CREATE_NO_WINDOW` dá ao filho um console oculto, que os netos herdam. Todo
`subprocess.run` do pacote passa por aqui (há teste cobrando).
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

CREATE_NO_WINDOW = 0x08000000


def quiet_kwargs() -> dict[str, Any]:
    """Argumentos extras de `subprocess` para não abrir janela; vazio fora do Windows."""
    if sys.platform == "win32":
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def run_quiet(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run` sem janela. Flags de criação do chamador são preservadas."""
    if sys.platform == "win32":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(argv, **kwargs)
