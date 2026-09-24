"""Registro do RAGX como servidor MCP nos clientes instalados na máquina.

Fica FORA de `ragx.mcp` de propósito: aquele pacote não pode tocar em
filesystem (ADR-0006, verificado por `tests/security/test_architecture.py`).
Registrar um servidor é tarefa de instalação, não de servir MCP.

Também fica fora dos instaladores de shell. `install.sh` embutia um script
Python entre aspas e `install.ps1` reimplementava a mesma lógica em
PowerShell — duas implementações, nenhuma testada, e só uma delas sabia fazer
backup. Agora as duas chamam `ragx mcp install`.
"""

from ragx.clients.registry import (
    CLIENTS,
    Client,
    Outcome,
    Result,
    detect,
    register,
    register_all,
    unregister,
    unregister_all,
)

__all__ = [
    "CLIENTS",
    "Client",
    "Outcome",
    "Result",
    "detect",
    "register",
    "register_all",
    "unregister",
    "unregister_all",
]
