"""Mantém os hooks do RAGX em dia nos perfis do Claude Code onde ele já está ligado.

`ragx claude on` instala o MCP e os três hooks (dica de início de sessão, aviso de edição e lembrete
de busca), mas quem ligou numa versão antiga ficou sem os dois últimos, e nada avisava: o índice
deixava de ver as edições do agente. `heal` completa o que falta, só em perfil onde o MCP está
registrado, e respeita a escolha explícita (`ragx claude on --no-touch`), que fica em
`~/.ragx/claude-optout.json`. Nunca liga o RAGX num perfil desligado: isso é decisão da pessoa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ragx.clients.claude_hint import (
    has_hint,
    has_nudge_hook,
    has_touch_hook,
    install_hint,
    install_nudge_hook,
    install_touch_hook,
)
from ragx.clients.registry import Client, Outcome, Result, _escrever, _home, is_registered

PARTES = ("hint", "touch", "nudge")


def optout_file(home: Path | None = None) -> Path:
    return (home or _home()) / ".ragx" / "claude-optout.json"


def _ler_optout(home: Path | None = None) -> dict[str, list[str]]:
    try:
        dados = json.loads(optout_file(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    perfis = dados.get("profiles") if isinstance(dados, dict) else None
    if not isinstance(perfis, dict):
        return {}
    return {
        str(pid): [p for p in partes if p in PARTES]
        for pid, partes in perfis.items()
        if isinstance(partes, list)
    }


def optout_of(client_id: str, home: Path | None = None) -> set[str]:
    """As partes que a pessoa recusou neste perfil (`--no-touch` etc.)."""
    return set(_ler_optout(home).get(client_id, []))


def record_choice(client_id: str, escolhas: dict[str, bool], home: Path | None = None) -> None:
    """Guarda o que `ragx claude on` pediu: `False` vira recusa, `True` a apaga. Sem mudança, não grava."""
    atual = _ler_optout(home)
    recusadas = set(atual.get(client_id, []))
    for parte, quer in escolhas.items():
        if parte not in PARTES:
            continue
        if quer:
            recusadas.discard(parte)
        else:
            recusadas.add(parte)
    if recusadas == set(atual.get(client_id, [])):
        return
    if recusadas:
        atual[client_id] = sorted(recusadas)
    else:
        atual.pop(client_id, None)
    alvo = optout_file(home)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    _escrever(alvo, json.dumps({"profiles": atual}, indent=2, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class Healed:
    client: Client
    installed: tuple[str, ...]
    skipped: tuple[str, ...]  # recusados pela pessoa
    failed: tuple[str, ...]


def heal_profile(client: Client, command: str = "ragx", dry_run: bool = False, home: Path | None = None) -> Healed:
    """Instala o que falta num perfil ligado. Perfil desligado não é tocado."""
    if not is_registered(client):
        return Healed(client, (), (), ())
    recusadas = optout_of(client.id, home)
    tem = {"hint": has_hint, "touch": has_touch_hook, "nudge": has_nudge_hook}
    instalar = {"hint": install_hint, "touch": install_touch_hook, "nudge": install_nudge_hook}
    feitos: list[str] = []
    pulados: list[str] = []
    falhas: list[str] = []
    for parte in PARTES:
        if parte in recusadas:
            pulados.append(parte)
            continue
        if tem[parte](client):
            continue
        r: Result = instalar[parte](client, command=command, dry_run=dry_run)
        if r.ok and r.outcome in (Outcome.CREATED, Outcome.UPDATED):
            feitos.append(parte)
        elif not r.ok:
            falhas.append(parte)
    return Healed(client, tuple(feitos), tuple(pulados), tuple(falhas))

