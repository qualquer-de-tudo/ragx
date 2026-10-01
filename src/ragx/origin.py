"""Quem está rodando este processo, se for o Claude Code (só stdlib).

Fica fora de `ragx.clients` de propósito: `ragx/clients/__init__.py` importa o `registry` inteiro, e
os hooks que rodam em toda sessão (`ragx.hooklight`, RAGX-0143) não podem pagar isso só para
descobrir o perfil. `ragx.clients.registry` reexporta as duas funções.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping


def profile_name(config_dir: str | None) -> str:
    """Nome curto do perfil: `padrão`, `empresa` (de `~/.claude-empresa`) ou o nome da pasta."""
    if not config_dir or not config_dir.strip():
        return "padrão"
    # Os dois separadores, em qualquer sistema: `Path` no Linux e no macOS não
    # corta em `\`, e um caminho do Windows virava o nome inteiro do perfil.
    nome = re.split(r"[\\/]", config_dir.strip().rstrip("\\/"))[-1]
    if nome in ("", ".claude"):
        return "padrão"
    return nome.removeprefix(".claude-").lstrip(".") or nome


def claude_origin(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Quem está rodando este processo, se for o Claude Code.

    O Claude Code passa `CLAUDECODE=1` e `CLAUDE_CODE_SESSION_ID` aos processos
    que abre (servidor MCP, hooks, o terminal do agente), e o perfil vem do
    `CLAUDE_CONFIG_DIR` que ele mesmo herdou. Fora do Claude Code, vazio: sem
    essas variáveis não dá para dizer quem chamou, e um palpite apareceria no
    painel como fato.
    """
    env = os.environ if environ is None else environ
    if env.get("CLAUDECODE") != "1":
        return {}
    out = {"client": "claude-code", "profile": profile_name(env.get("CLAUDE_CONFIG_DIR"))}
    sessao = env.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if sessao:
        # O suficiente para agrupar as chamadas de uma sessão; o id inteiro não serve a mais nada aqui.
        out["session"] = sessao[:8]
    return out
