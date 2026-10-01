"""Hook `SessionStart` do Claude Code que diz ao agente que o projeto tem RAGX.

Registrar o servidor MCP não bastou. As ferramentas do RAGX chegam ao agente
como *deferred* (só o nome; o schema exige um ToolSearch antes), e as
instruções do servidor são genéricas. Em 14 dias de uso real, com o servidor
registrado, o agente abriu ~50 sessões e chamou o RAGX 4 vezes, todas no
próprio repositório do RAGX, o único cujo AGENTS.md mandava usar. Grep e Read já
estão carregados; o RAGX não. O modelo vai no que está à mão.

O hook resolve isso na hora certa e só onde faz sentido: no início da sessão,
`ragx claude hint` olha a pasta, e só fala se houver índice (ou projetos
indexados abaixo dela). Fora de projeto RAGX, fica calado.

Mesmas regras de `registry`: alteração mínima no `settings.json` da pessoa,
idempotente, backup antes de mudar, JSON inválido não é sobrescrito.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ragx import hooklight
from ragx.clients.registry import (
    Client,
    Outcome,
    Result,
    _backup,
    _escrever,
    claude_settings,
)

EVENT = "SessionStart"
#: O segundo hook (RAGX-0141): depois de cada edição de arquivo, avisa o RAGX para reindexá-lo.
TOUCH_EVENT = "PostToolUse"
TOUCH_MATCHER = "Edit|Write|MultiEdit"

#: Reconhece a entrada do RAGX mesmo que o executável gravado mude de lugar.
_NOSSO = re.compile(r"ragx(\.exe)?\"?\s+claude\s+hint\s*$", re.IGNORECASE)
_NOSSO_TOUCH = re.compile(r"ragx(\.exe)?\"?\s+touch\s+--stdin-json\s*$", re.IGNORECASE)


def hint_command(command: str) -> str:
    """`ragx claude hint`, com o executável que o MCP também usa.

    Caminho absoluto vai com barras normais e entre aspas: no Windows o Claude
    Code roda hooks pelo Git Bash quando ele existe, e `\\` dentro de aspas
    duplas ainda é escape no bash para alguns caracteres.
    """
    exe = command.replace("\\", "/")
    if any(ch in exe for ch in " /"):
        exe = f'"{exe}"'
    return f"{exe} claude hint"


def _eh_nosso(hook: Any) -> bool:
    return isinstance(hook, dict) and bool(_NOSSO.search(str(hook.get("command", ""))))


def _eh_nosso_touch(hook: Any) -> bool:
    return isinstance(hook, dict) and bool(_NOSSO_TOUCH.search(str(hook.get("command", ""))))


def _ler(path: Path, client: Client) -> tuple[dict[str, Any] | None, Result | None]:
    if not path.is_file():
        return {}, None
    bruto = path.read_text(encoding="utf-8")
    if not bruto.strip():
        return {}, None
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        return None, Result(
            client, Outcome.FAILED,
            f"{path} não é JSON válido (linha {exc.lineno}). Não vou sobrescrever.",
        )
    if not isinstance(dados, dict):
        return None, Result(client, Outcome.FAILED, f"{path} não contém um objeto JSON no topo.")
    return dados, None


def _grupos(
    dados: dict[str, Any], path: Path, client: Client, event: str = EVENT
) -> tuple[list[Any] | None, Result | None]:
    hooks = dados.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        return None, Result(client, Outcome.FAILED, f"`hooks` em {path} não é um objeto — não vou mexer.")
    grupos = (hooks or {}).get(event)
    if grupos is not None and not isinstance(grupos, list):
        return None, Result(client, Outcome.FAILED, f"`hooks.{event}` em {path} não é uma lista — não vou mexer.")
    return list(grupos or []), None


def _sem_o_nosso(grupos: list[Any], eh_nosso: Any = _eh_nosso) -> list[Any]:
    """Tira só a nossa entrada; grupo que ficar vazio sai junto."""
    out: list[Any] = []
    for grupo in grupos:
        if not isinstance(grupo, dict) or not isinstance(grupo.get("hooks"), list):
            out.append(grupo)
            continue
        resto = [h for h in grupo["hooks"] if not eh_nosso(h)]
        if len(resto) == len(grupo["hooks"]):
            out.append(grupo)
        elif resto:
            out.append({**grupo, "hooks": resto})
    return out


def _gravar(
    path: Path, dados: dict[str, Any], grupos: list[Any], existia: bool, event: str = EVENT
) -> Path | None:
    hooks = dict(dados.get("hooks") or {})
    if grupos:
        hooks[event] = grupos
    else:
        hooks.pop(event, None)
    if hooks:
        dados["hooks"] = hooks
    else:
        dados.pop("hooks", None)
    backup = _backup(path) if existia else None
    path.parent.mkdir(parents=True, exist_ok=True)
    _escrever(path, json.dumps(dados, indent=2, ensure_ascii=False) + "\n")
    return backup


def install_hint(client: Client, command: str = "ragx", dry_run: bool = False) -> Result:
    """Põe (ou corrige) o hook de dica no `settings.json` do perfil."""
    path = claude_settings(client)
    try:
        dados, falha = _ler(path, client)
        if falha or dados is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")
        grupos, falha = _grupos(dados, path, client)
        if falha or grupos is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")

        nova = {"type": "command", "command": hint_command(command), "timeout": 15}
        atuais = [h for g in grupos if isinstance(g, dict) for h in g.get("hooks") or [] if _eh_nosso(h)]
        if atuais == [nova]:
            return Result(client, Outcome.UNCHANGED, "dica de sessão já instalada")

        novos = [*_sem_o_nosso(grupos), {"hooks": [nova]}]
        existia = path.is_file()
        backup = None if dry_run else _gravar(path, dados, novos, existia)
        return Result(
            client, Outcome.UPDATED if existia else Outcome.CREATED,
            f"dica de sessão instalada em {path.name}", backup,
        )
    except OSError as exc:
        return Result(client, Outcome.FAILED, f"não consegui escrever {path}: {exc}")


def remove_hint(client: Client, dry_run: bool = False) -> Result:
    """Tira só o hook do RAGX; os hooks da pessoa ficam."""
    path = claude_settings(client)
    try:
        dados, falha = _ler(path, client)
        if falha or dados is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")
        grupos, falha = _grupos(dados, path, client)
        if falha or grupos is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")
        novos = _sem_o_nosso(grupos)
        if novos == grupos:
            return Result(client, Outcome.UNCHANGED, "dica de sessão não estava instalada")
        backup = None if dry_run else _gravar(path, dados, novos, True)
        return Result(client, Outcome.REMOVED, f"dica de sessão removida de {path.name}", backup)
    except OSError as exc:
        return Result(client, Outcome.FAILED, f"não consegui escrever {path}: {exc}")


def has_hint(client: Client) -> bool:
    path = claude_settings(client)
    try:
        dados = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return False
    grupos = ((dados or {}).get("hooks") or {}).get(EVENT) if isinstance(dados, dict) else None
    if not isinstance(grupos, list):
        return False
    return any(_eh_nosso(h) for g in grupos if isinstance(g, dict) for h in g.get("hooks") or [])


# ── o hook de toque (PostToolUse) ───────────────────────────────────────
def touch_command(command: str) -> str:
    """`ragx touch --stdin-json`, com o mesmo executável (e as mesmas aspas) do hint."""
    return hint_command(command).replace(" claude hint", " touch --stdin-json")


def _entrada_de_toque(command: str) -> dict[str, Any]:
    """`async`: o agente não espera a reindexação; `timeout` curto: só enfileira e dispara."""
    return {
        "matcher": TOUCH_MATCHER,
        "hooks": [{"type": "command", "command": touch_command(command), "async": True, "timeout": 10}],
    }


def install_touch_hook(client: Client, command: str = "ragx", dry_run: bool = False) -> Result:
    """Põe (ou corrige) o hook `PostToolUse` que avisa o RAGX das edições do agente."""
    path = claude_settings(client)
    try:
        dados, falha = _ler(path, client)
        if falha or dados is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")
        grupos, falha = _grupos(dados, path, client, TOUCH_EVENT)
        if falha or grupos is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")

        nova = _entrada_de_toque(command)
        atuais = [
            g for g in grupos
            if isinstance(g, dict) and any(_eh_nosso_touch(h) for h in g.get("hooks") or [])
        ]
        if atuais == [nova]:
            return Result(client, Outcome.UNCHANGED, "aviso de edição já instalado")

        novos = [*_sem_o_nosso(grupos, _eh_nosso_touch), nova]
        existia = path.is_file()
        backup = None if dry_run else _gravar(path, dados, novos, existia, TOUCH_EVENT)
        return Result(
            client, Outcome.UPDATED if existia else Outcome.CREATED,
            f"aviso de edição instalado em {path.name}", backup,
        )
    except OSError as exc:
        return Result(client, Outcome.FAILED, f"não consegui escrever {path}: {exc}")


def remove_touch_hook(client: Client, dry_run: bool = False) -> Result:
    """Tira só o hook de toque do RAGX; os hooks da pessoa (inclusive `PostToolUse`) ficam."""
    path = claude_settings(client)
    try:
        dados, falha = _ler(path, client)
        if falha or dados is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")
        grupos, falha = _grupos(dados, path, client, TOUCH_EVENT)
        if falha or grupos is None:
            return falha or Result(client, Outcome.FAILED, "configuração ilegível")
        novos = _sem_o_nosso(grupos, _eh_nosso_touch)
        if novos == grupos:
            return Result(client, Outcome.UNCHANGED, "aviso de edição não estava instalado")
        backup = None if dry_run else _gravar(path, dados, novos, True, TOUCH_EVENT)
        return Result(client, Outcome.REMOVED, f"aviso de edição removido de {path.name}", backup)
    except OSError as exc:
        return Result(client, Outcome.FAILED, f"não consegui escrever {path}: {exc}")


def has_touch_hook(client: Client) -> bool:
    path = claude_settings(client)
    try:
        dados = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return False
    grupos = ((dados or {}).get("hooks") or {}).get(TOUCH_EVENT) if isinstance(dados, dict) else None
    if not isinstance(grupos, list):
        return False
    return any(_eh_nosso_touch(h) for g in grupos if isinstance(g, dict) for h in g.get("hooks") or [])


# ── o texto (uma só fonte: `ragx.hooklight`, que roda sem importar a CLI) ──
_FERRAMENTAS = hooklight.FERRAMENTAS


def hint_text(start: Path | None = None) -> str:
    """O que o agente lê no início da sessão. Vazio fora de projeto RAGX."""
    return hooklight.hint_text(start)


def record_session_start(start: Path | None = None) -> None:
    """Uma sessão do Claude Code abriu num projeto indexado: vira evento na tela de atividade."""
    hooklight.record_session_start(start)
