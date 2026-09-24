"""Onde cada cliente MCP guarda sua configuração, e como alterá-la sem estragar.

A regra que governa este módulo: **a configuração é da pessoa, não nossa.**
O arquivo pode ter dez servidores MCP, comentários e ajustes que nada têm a ver
com o RAGX. Um instalador que reescreve o arquivo inteiro destrói tudo isso — e
descobrir que foi o instalador é quase impossível depois do fato.

Daí as quatro regras de cada gravação:

1. **Alteração mínima.** Mexe-se numa chave: o servidor `ragx`. O resto do
   documento é preservado como está.
2. **Idempotência.** Se a entrada já é exatamente a que escreveríamos, nada é
   escrito e nada é salvo em backup. Rodar de novo não duplica nem suja.
3. **Backup antes de mudar.** Só quando algo vai mudar de verdade.
4. **Configuração inválida não é sobrescrita.** JSON quebrado pode ser o
   arquivo que a pessoa está editando agora. Recusar e explicar é melhor do que
   apagar.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

#: Nome do servidor dentro da configuração de cada cliente.
SERVER_NAME = "ragx"


class Outcome(StrEnum):
    CREATED = "created"      # o arquivo não existia; foi criado
    UPDATED = "updated"      # o arquivo existia; a entrada `ragx` mudou
    UNCHANGED = "unchanged"  # já estava exatamente assim
    ABSENT = "absent"        # o cliente não está instalado nesta máquina
    REMOVED = "removed"      # a entrada `ragx` foi retirada da configuração
    FAILED = "failed"        # sem permissão, ou configuração ilegível


@dataclass(frozen=True, slots=True)
class Client:
    id: str
    label: str
    #: Caminho da configuração, relativo a `$HOME` salvo indicação em contrário.
    config: Path
    #: `json` para quase todos; o Codex CLI usa TOML.
    fmt: str
    #: Chave que contém o mapa de servidores.
    key: str
    #: Caminhos cuja existência prova que o cliente está instalado.
    #:
    #: Normalmente é o diretório da configuração — um cliente recém instalado
    #: pode ainda não ter escrito o `mcp.json`, e criar esse diretório por
    #: conta própria espalharia pastas de clientes que a pessoa não usa.
    #:
    #: Mas o Claude Code guarda a configuração em `~/.claude.json`, cujo
    #: diretório-pai é o `$HOME` — que existe sempre. Usar o pai ali daria
    #: "instalado" em toda máquina do mundo, e o registro criaria um
    #: `~/.claude.json` para quem nunca usou o Claude Code. Para esses casos a
    #: prova é outra: o próprio arquivo, ou um diretório irmão.
    markers: tuple[Path, ...] = ()

    @property
    def installed(self) -> bool:
        alvos = self.markers or (self.config.parent,)
        return self.config.is_file() or any(p.exists() for p in alvos)


@dataclass(frozen=True, slots=True)
class Result:
    client: Client
    outcome: Outcome
    detail: str = ""
    backup: Path | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is not Outcome.FAILED


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _claude_desktop_config() -> Path:
    """O Claude Desktop guarda a configuração em lugar diferente por sistema."""
    home = _home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def _clients() -> tuple[Client, ...]:
    home = _home()
    return (
        Client(
            "claude-desktop", "Claude Desktop",
            _claude_desktop_config(), "json", "mcpServers",
        ),
        Client(
            "claude-code", "Claude Code",
            home / ".claude.json", "json", "mcpServers",
            # `~/.claude/` é criado pelo Claude Code; o `$HOME` não prova nada.
            markers=(home / ".claude",),
        ),
        Client(
            "cursor", "Cursor",
            home / ".cursor" / "mcp.json", "json", "mcpServers",
        ),
        Client(
            "windsurf", "Windsurf",
            home / ".codeium" / "windsurf" / "mcp_config.json", "json", "mcpServers",
        ),
        Client(
            "gemini", "Gemini CLI",
            home / ".gemini" / "settings.json", "json", "mcpServers",
        ),
        Client(
            # O Codex é o único em TOML, com a chave em snake_case.
            "codex", "Codex CLI",
            home / ".codex" / "config.toml", "toml", "mcp_servers",
        ),
    )


def CLIENTS() -> tuple[Client, ...]:  # noqa: N802 - lido como constante
    """Os clientes suportados, resolvidos para ESTA máquina.

    É função, e não constante de módulo, porque os caminhos dependem de `$HOME`
    e de `%APPDATA%`. Congelá-los no import tornaria o módulo intestável: a
    suíte redireciona o HOME e a lista continuaria apontando para a máquina de
    verdade.
    """
    return _clients()


def detect() -> list[Client]:
    """Só os clientes que existem aqui."""
    return [c for c in CLIENTS() if c.installed]


# ── JSON ────────────────────────────────────────────────────────────────
def _entrada(command: str, args: list[str]) -> dict[str, Any]:
    return {"command": command, "args": list(args)}


def _aplicar_json(
    client: Client, command: str, args: list[str], dry_run: bool
) -> Result:
    existia = client.config.is_file()
    dados: dict[str, Any] = {}

    if existia:
        bruto = client.config.read_text(encoding="utf-8")
        if bruto.strip():
            try:
                carregado = json.loads(bruto)
            except json.JSONDecodeError as exc:
                return Result(
                    client, Outcome.FAILED,
                    f"{client.config} não é JSON válido (linha {exc.lineno}). "
                    f"Não vou sobrescrever — corrija o arquivo e rode de novo.",
                )
            if not isinstance(carregado, dict):
                return Result(
                    client, Outcome.FAILED,
                    f"{client.config} não contém um objeto JSON no topo.",
                )
            dados = carregado

    servidores = dados.get(client.key)
    if servidores is not None and not isinstance(servidores, dict):
        return Result(
            client, Outcome.FAILED,
            f"`{client.key}` em {client.config} não é um objeto — não vou mexer.",
        )
    servidores = dict(servidores or {})

    nova = _entrada(command, args)
    if servidores.get(SERVER_NAME) == nova:
        return Result(client, Outcome.UNCHANGED, "já registrado, igualzinho")

    backup = None if dry_run else _backup(client.config) if existia else None
    servidores[SERVER_NAME] = nova
    dados[client.key] = servidores

    if not dry_run:
        try:
            client.config.parent.mkdir(parents=True, exist_ok=True)
            _escrever(
                client.config,
                json.dumps(dados, indent=2, ensure_ascii=False) + "\n",
            )
        except OSError as exc:
            return Result(client, Outcome.FAILED, f"não consegui escrever: {exc}")

    return Result(
        client,
        Outcome.UPDATED if existia else Outcome.CREATED,
        f"servidor `{SERVER_NAME}` registrado em `{client.key}`",
        backup,
    )


# ── TOML (Codex CLI) ────────────────────────────────────────────────────
def _bloco_toml(key: str, command: str, args: list[str]) -> str:
    argumentos = ", ".join(json.dumps(a) for a in args)
    return (
        f"[{key}.{SERVER_NAME}]\n"
        f"command = {json.dumps(command)}\n"
        f"args = [{argumentos}]\n"
    )


def _aplicar_toml(
    client: Client, command: str, args: list[str], dry_run: bool
) -> Result:
    """Edita só a tabela `[mcp_servers.ragx]`.

    A biblioteca padrão lê TOML (`tomllib`) mas não escreve. Reserializar com
    um escritor de terceiros reformataria o arquivo inteiro e apagaria os
    comentários da pessoa. Como o alvo é UMA tabela com forma conhecida,
    substituir o trecho por texto é a alteração mais contida possível.
    """
    import tomllib

    existia = client.config.is_file()
    original = client.config.read_text(encoding="utf-8") if existia else ""

    if original.strip():
        try:
            atual = tomllib.loads(original)
        except tomllib.TOMLDecodeError as exc:
            return Result(
                client, Outcome.FAILED,
                f"{client.config} não é TOML válido ({exc}). "
                f"Não vou sobrescrever — corrija o arquivo e rode de novo.",
            )
        registrado = (atual.get(client.key) or {}).get(SERVER_NAME)
        if registrado == {"command": command, "args": list(args)}:
            return Result(client, Outcome.UNCHANGED, "já registrado, igualzinho")

    bloco = _bloco_toml(client.key, command, args)
    # A tabela vai do cabeçalho até o próximo cabeçalho de tabela, ou ao fim.
    cabecalho = re.compile(
        rf"^\[{re.escape(client.key)}\.{re.escape(SERVER_NAME)}\]\s*$", re.M
    )
    achado = cabecalho.search(original)
    if achado:
        resto = original[achado.end() :]
        proxima = re.search(r"^\[", resto, re.M)
        fim = achado.end() + (proxima.start() if proxima else len(resto))
        novo = original[: achado.start()] + bloco + original[fim:]
    else:
        prefixo = original if not original or original.endswith("\n") else original + "\n"
        novo = (prefixo + "\n" if prefixo.strip() else prefixo) + bloco

    if novo == original:
        return Result(client, Outcome.UNCHANGED, "já registrado, igualzinho")

    backup = None if dry_run else _backup(client.config) if existia else None
    if not dry_run:
        try:
            client.config.parent.mkdir(parents=True, exist_ok=True)
            _escrever(client.config, novo)
        except OSError as exc:
            return Result(client, Outcome.FAILED, f"não consegui escrever: {exc}")

    return Result(
        client,
        Outcome.UPDATED if existia else Outcome.CREATED,
        f"tabela `[{client.key}.{SERVER_NAME}]` registrada",
        backup,
    )


# ── utilidades ──────────────────────────────────────────────────────────
def _backup(destino: Path) -> Path | None:
    """Cópia datada ao lado do original. Falha em backup não impede o registro,
    mas é reportada — o que não pode acontecer é achar que houve backup."""
    alvo = destino.with_name(f"{destino.name}.ragx-backup-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        shutil.copy2(destino, alvo)
        return alvo
    except OSError:
        return None


def _escrever(destino: Path, conteudo: str) -> None:
    """Escrita atômica: grava ao lado e troca.

    Escrever por cima do arquivo deixa uma janela em que ele está truncado. Se
    a máquina desligar ali, a pessoa perde a configuração de TODOS os servidores
    MCP dela, não só a do RAGX.

    A troca também não pode afrouxar permissões: esses arquivos costumam
    guardar tokens de outros servidores MCP. Se o destino existe, o temporário
    herda o modo dele; se não existe, nasce legível só pelo dono (0600 no
    POSIX; no Windows o modo só controla o bit de somente leitura).
    """
    temp = destino.with_name(f"{destino.name}.ragx-tmp")
    with contextlib.suppress(FileNotFoundError):
        temp.unlink()  # sobra de uma escrita interrompida manteria o modo antigo
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(conteudo)
    if destino.exists():
        shutil.copymode(destino, temp)
    os.replace(temp, destino)


def register(
    client: Client,
    command: str = "ragx",
    args: list[str] | None = None,
    dry_run: bool = False,
) -> Result:
    """Registra (ou atualiza) o RAGX na configuração de um cliente."""
    args = list(args if args is not None else ["mcp", "serve"])
    if not client.installed:
        return Result(client, Outcome.ABSENT, "não encontrado nesta máquina")
    try:
        if client.fmt == "toml":
            return _aplicar_toml(client, command, args, dry_run)
        return _aplicar_json(client, command, args, dry_run)
    except PermissionError as exc:
        return Result(client, Outcome.FAILED, f"sem permissão: {exc}")
    except OSError as exc:
        return Result(client, Outcome.FAILED, str(exc))


def register_all(
    command: str = "ragx",
    args: list[str] | None = None,
    dry_run: bool = False,
    only: list[str] | None = None,
) -> list[Result]:
    """Todos os clientes conhecidos, ou só os pedidos em `only`.

    Cliente ausente vira `ABSENT`, não erro: não ter o Windsurf instalado é o
    caso comum, e tratar isso como falha faria todo instalador terminar em
    vermelho.
    """
    alvos = CLIENTS()
    if only:
        pedidos = {c.strip().lower() for c in only}
        alvos = tuple(c for c in alvos if c.id in pedidos)
    return [register(c, command, args, dry_run) for c in alvos]


def is_registered(client: Client) -> bool:
    """O RAGX está na configuração deste cliente agora? Só lê, nunca escreve."""
    if not client.config.is_file():
        return False
    try:
        bruto = client.config.read_text(encoding="utf-8")
        if client.fmt == "toml":
            import tomllib

            servidores = tomllib.loads(bruto).get(client.key)
        else:
            dados = json.loads(bruto) if bruto.strip() else {}
            servidores = dados.get(client.key) if isinstance(dados, dict) else None
    except (OSError, ValueError):
        return False
    return isinstance(servidores, dict) and SERVER_NAME in servidores


# ── remoção ─────────────────────────────────────────────────────────────
def _remover_json(client: Client, dry_run: bool) -> Result:
    if not client.config.is_file():
        return Result(client, Outcome.UNCHANGED, "não estava registrado")
    bruto = client.config.read_text(encoding="utf-8")
    if not bruto.strip():
        return Result(client, Outcome.UNCHANGED, "não estava registrado")
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        return Result(
            client, Outcome.FAILED,
            f"{client.config} não é JSON válido (linha {exc.lineno}). "
            f"Não vou sobrescrever — corrija o arquivo e rode de novo.",
        )
    if not isinstance(dados, dict):
        return Result(
            client, Outcome.FAILED,
            f"{client.config} não contém um objeto JSON no topo.",
        )
    servidores = dados.get(client.key)
    if servidores is not None and not isinstance(servidores, dict):
        return Result(
            client, Outcome.FAILED,
            f"`{client.key}` em {client.config} não é um objeto — não vou mexer.",
        )
    if not servidores or SERVER_NAME not in servidores:
        return Result(client, Outcome.UNCHANGED, "não estava registrado")

    backup = None if dry_run else _backup(client.config)
    del servidores[SERVER_NAME]
    if not dry_run:
        try:
            _escrever(
                client.config,
                json.dumps(dados, indent=2, ensure_ascii=False) + "\n",
            )
        except OSError as exc:
            return Result(client, Outcome.FAILED, f"não consegui escrever: {exc}")
    return Result(
        client, Outcome.REMOVED,
        f"servidor `{SERVER_NAME}` removido de `{client.key}`", backup,
    )


def _remover_toml(client: Client, dry_run: bool) -> Result:
    """Retira só a tabela `[mcp_servers.ragx]` (e subtabelas dela), por texto."""
    import tomllib

    if not client.config.is_file():
        return Result(client, Outcome.UNCHANGED, "não estava registrado")
    original = client.config.read_text(encoding="utf-8")
    if not original.strip():
        return Result(client, Outcome.UNCHANGED, "não estava registrado")
    try:
        atual = tomllib.loads(original)
    except tomllib.TOMLDecodeError as exc:
        return Result(
            client, Outcome.FAILED,
            f"{client.config} não é TOML válido ({exc}). "
            f"Não vou sobrescrever — corrija o arquivo e rode de novo.",
        )
    if SERVER_NAME not in (atual.get(client.key) or {}):
        return Result(client, Outcome.UNCHANGED, "não estava registrado")

    alvo = f"{client.key}.{SERVER_NAME}"
    cabecalho = re.compile(rf"^\[{re.escape(alvo)}\]\s*$", re.M)
    achado = cabecalho.search(original)
    if not achado:  # forma inline/dotted: fora do que sabemos editar por texto
        return Result(
            client, Outcome.FAILED,
            f"`{alvo}` está numa forma que não sei remover com segurança — não vou mexer.",
        )
    resto = original[achado.end() :]
    # Próximo cabeçalho que não seja subtabela do próprio `ragx`.
    proxima = re.search(rf"^\[(?!{re.escape(alvo)}[.\]])", resto, re.M)
    fim = achado.end() + (proxima.start() if proxima else len(resto))
    # Comentários logo acima do próximo cabeçalho pertencem a ele, não ao `ragx`.
    comentarios = re.search(r"(?:^[ \t]*#.*\n)+\Z", original[achado.end() : fim], re.M)
    if comentarios:
        fim = achado.end() + comentarios.start()
    novo = original[: achado.start()] + original[fim:]

    backup = None if dry_run else _backup(client.config)
    if not dry_run:
        try:
            _escrever(client.config, novo)
        except OSError as exc:
            return Result(client, Outcome.FAILED, f"não consegui escrever: {exc}")
    return Result(client, Outcome.REMOVED, f"tabela `[{alvo}]` removida", backup)


def unregister(client: Client, dry_run: bool = False) -> Result:
    """Retira o RAGX da configuração de um cliente. Idempotente."""
    if not client.installed:
        return Result(client, Outcome.ABSENT, "não encontrado nesta máquina")
    try:
        if client.fmt == "toml":
            return _remover_toml(client, dry_run)
        return _remover_json(client, dry_run)
    except PermissionError as exc:
        return Result(client, Outcome.FAILED, f"sem permissão: {exc}")
    except OSError as exc:
        return Result(client, Outcome.FAILED, str(exc))


def unregister_all(
    dry_run: bool = False,
    only: list[str] | None = None,
) -> list[Result]:
    """Espelho de `register_all` para a remoção."""
    alvos = CLIENTS()
    if only:
        pedidos = {c.strip().lower() for c in only}
        alvos = tuple(c for c in alvos if c.id in pedidos)
    return [unregister(c, dry_run) for c in alvos]
