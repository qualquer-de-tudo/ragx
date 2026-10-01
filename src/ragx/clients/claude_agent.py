"""O subagente `ragx-explorer`, instalável no perfil do Claude Code (RAGX-0161).

Explorar código num repositório grande enche o contexto do agente principal com leituras que ele não
vai reusar. Um subagente isola a exploração e devolve só o resumo, e põe o RAGX NO CAMINHO do modelo em
vez de depender de ele lembrar (3 de 38 sessões chamaram o RAGX). O RAGX não instalava nenhum subagente.

Opt-in: um subagente novo aparece na lista da pessoa, então só `ragx claude agent install` (ou
`ragx claude on --agent`) o cria. O arquivo mora no perfil (`<perfil>/agents/ragx-explorer.md`), nunca
no repositório do usuário, e leva o marcador `<!-- ragx:managed v1 -->`: só o arquivo com o marcador é
atualizado ou removido; um arquivo da pessoa com o mesmo nome nunca é sobrescrito.
"""

from __future__ import annotations

import json
from pathlib import Path

from ragx.clients.registry import (
    Client,
    Outcome,
    Result,
    _backup,
    _escrever,
    claude_settings,
)

NAME = "ragx-explorer"
MARKER = "<!-- ragx:managed v1 -->"

#: Só leitura (sem `Edit`, `Write` nem `Bash`). Os `mcp__ragx__*` existem nos dois perfis do servidor.
TOOLS = (
    "mcp__ragx__build_context",
    "mcp__ragx__search_hybrid",
    "mcp__ragx__get_chunk",
    "mcp__ragx__get_entity",
    "Read",
    "Grep",
    "Glob",
)

#: Entra no contexto do agente principal em TODA sessão: curta de propósito (≤ 60 tokens).
DESCRIPTION = (
    "Explora e localiza código no projeto sem encher o seu contexto. Acha onde algo está e como funciona "
    "e devolve só um resumo curto. Prefira-o a ler vários arquivos."
)

_BODY = f"""{MARKER}

Você explora código para outro agente e devolve só o resumo: é isso que poupa o contexto dele.

1. Comece pelo RAGX: `mcp__ragx__build_context(query)` monta o contexto da pergunta; use
   `mcp__ragx__search_hybrid(query)` para só localizar, `mcp__ragx__get_chunk(id)` para abrir um trecho e
   `mcp__ragx__get_entity(nome)` para ver quem chama quem. Se as ferramentas aparecerem só pelo nome,
   carregue-as com ToolSearch antes.
2. Use `Read`, `Grep` e `Glob` só nos arquivos que o RAGX apontou, para confirmar ou aprofundar.
3. Responda curto: os caminhos com as linhas (`src/a.py:10-42`) e de 3 a 6 frases sobre o que importa.
   Não cole trechos longos de código; quem pediu abre o arquivo se precisar.
4. Você só lê. Não edite arquivos nem rode comandos.
"""


def agent_text() -> str:
    """O arquivo inteiro: frontmatter YAML, marcador e instruções."""
    ferramentas = ", ".join(TOOLS)
    # a descrição entre aspas (JSON é YAML válido): um `: ` no texto quebraria o frontmatter
    descricao = json.dumps(DESCRIPTION, ensure_ascii=False)
    return f"---\nname: {NAME}\ndescription: {descricao}\ntools: {ferramentas}\n---\n{_BODY}"


def agent_path(client: Client) -> Path:
    """`<perfil>/agents/ragx-explorer.md`, na pasta do perfil do Claude Code (a do `settings.json`)."""
    return claude_settings(client).parent / "agents" / f"{NAME}.md"


def _nosso(path: Path) -> bool | None:
    """`True` se o arquivo é nosso (tem o marcador), `False` se é da pessoa, `None` se não existe."""
    try:
        return MARKER in path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        return False


def install_agent(client: Client, dry_run: bool = False) -> Result:
    path = agent_path(client)
    existente = _nosso(path)
    if existente is False:
        return Result(
            client, Outcome.FAILED,
            f"{path} já existe e não é do RAGX (sem o marcador `{MARKER}`): não vou sobrescrever. "
            "Renomeie o seu ou apague-o e rode de novo.",
        )
    texto = agent_text()
    try:
        if existente and path.read_text(encoding="utf-8") == texto:
            return Result(client, Outcome.UNCHANGED, "subagente ragx-explorer já instalado")
        backup = None
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            if existente:
                backup = _backup(path)
            _escrever(path, texto)
        return Result(
            client, Outcome.UPDATED if existente else Outcome.CREATED,
            f"subagente ragx-explorer instalado em {path}", backup,
        )
    except OSError as exc:
        return Result(client, Outcome.FAILED, f"não consegui escrever {path}: {exc}")


def remove_agent(client: Client, dry_run: bool = False) -> Result:
    """Apaga só o arquivo que tem o marcador; o da pessoa com o mesmo nome fica."""
    path = agent_path(client)
    existente = _nosso(path)
    if existente is None:
        return Result(client, Outcome.UNCHANGED, "subagente ragx-explorer não estava instalado")
    if existente is False:
        return Result(client, Outcome.UNCHANGED, f"{path} não é do RAGX: deixei como está")
    try:
        if not dry_run:
            path.unlink()
        return Result(client, Outcome.REMOVED, f"subagente ragx-explorer removido de {path.parent}")
    except OSError as exc:
        return Result(client, Outcome.FAILED, f"não consegui apagar {path}: {exc}")


def has_agent(client: Client) -> bool:
    return _nosso(agent_path(client)) is True
