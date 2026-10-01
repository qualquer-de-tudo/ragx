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
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from ragx.origin import claude_origin


def utcnow() -> str:
    """O mesmo formato de `ragx.storage.db.utcnow`, sem importar o banco (hooks leves, RAGX-0143)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

MAX_BYTES = 2 * 1024 * 1024

#: Teto de `mcp.jsonl` e `cli.jsonl` (RAGX-0174): acima disso o arquivo vira `<nome>.1` e recomeça. Sem teto, o
#: log crescia sem limite e o painel o relia inteiro a cada snapshot.
MAX_LOG_BYTES = 5 * 1024 * 1024
#: `[log] retain_days` quando quem chama não o conhece.
DEFAULT_RETAIN_DAYS = 14

#: Um por processo do servidor. Agrupa as linhas quando não há `session` (versões do
#: Claude Code sem a variável de ambiente): cada sessão sobe o seu servidor, então o
#: `proc` é, na prática, uma sessão (RAGX-0156).
_PROC = uuid.uuid4().hex[:8]
LOG_VERSION = 2


def mcp_entry(tool: str, ms: float, project: str, result: Any, text: str) -> dict[str, Any]:
    """A linha de telemetria de UMA chamada MCP (formato v2).

    A lógica fica aqui, fora de `ragx.mcp`, que não pode ler ambiente nem falar com o
    filesystem (ADR-0006). `text` é o texto EXATO que o cliente recebe. Nunca entram a
    consulta, os argumentos nem a mensagem de erro, que pode ecoar o argumento: só o
    `err_code`, que vem de um conjunto fixo.
    """
    from ragx.tokens import count_tokens

    entry: dict[str, Any] = {
        "v": LOG_VERSION,
        "ts": utcnow(),
        "tool": tool,
        "ms": ms,
        "project": project,
        "proc": _PROC,
    }
    ok = isinstance(result, dict) and result.get("ok") is True
    entry["ok"] = ok
    if not ok:
        erro = result.get("error") if isinstance(result, dict) else None
        codigo = erro.get("code") if isinstance(erro, dict) else None
        entry["err_code"] = str(codigo) if codigo else "unknown"
    dados = result.get("data") if isinstance(result, dict) else None
    if isinstance(dados, dict) and dados.get("dedupe_refs"):
        entry["dedupe_refs"] = int(dados["dedupe_refs"])
        entry["dedupe_saved_tokens"] = int(dados.get("dedupe_saved_tokens") or 0)
    entry["resp_chars"] = len(text)
    entry["resp_tokens"] = count_tokens(text)
    return entry


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


def log_mcp_call(state_dir: Path, entry: dict[str, Any], retain_days: int = DEFAULT_RETAIN_DAYS) -> None:
    """Grava telemetria de chamada MCP. Falha de log nunca vira falha adicional.

    A origem (Claude Code, qual perfil, qual sessão) entra aqui e não no
    servidor: vem do ambiente do processo, e `ragx.mcp` não lê o ambiente
    (ADR-0006). É o que deixa a tela de atividade do painel dizer quem chamou.
    """
    _append(state_dir, "mcp.jsonl", {**entry, **_origin()}, retain_days)


def log_cli_call(state_dir: Path, entry: dict[str, Any], retain_days: int = DEFAULT_RETAIN_DAYS) -> None:
    """Uma linha por comando de consulta da CLI (`.ragx/logs/cli.jsonl`).

    Nunca a consulta nem os argumentos: o painel mostra QUE houve uma busca,
    quando e por quem, não o que se buscou.
    """
    _append(state_dir, "cli.jsonl", {**entry, **_origin()}, retain_days)


def _origin() -> dict[str, str]:
    try:
        return claude_origin()
    except Exception:
        return {}


def _rotate(path: Path, retain_days: int) -> None:
    """Passa o log de `MAX_LOG_BYTES` para `<nome>.1` (substituindo o `.1` anterior) e apaga o `.1` velho demais.

    Melhor esforço, nunca levanta: no Windows outro processo pode estar com o arquivo aberto
    (`PermissionError`), e a rotação simplesmente tenta de novo na próxima escrita.
    """
    rotated = path.with_name(path.name + ".1")
    try:
        if path.stat().st_size > MAX_LOG_BYTES:
            os.replace(path, rotated)
    except OSError:
        pass
    try:
        if retain_days > 0 and time.time() - rotated.stat().st_mtime > retain_days * 86400:
            rotated.unlink()
    except OSError:
        pass


def _append(state_dir: Path, name: str, entry: dict[str, Any], retain_days: int = DEFAULT_RETAIN_DAYS) -> None:
    try:
        folder = Path(state_dir) / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        _rotate(path, retain_days)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_path(state_dir: Path) -> Path:
    return Path(state_dir) / "logs" / "errors.log"
