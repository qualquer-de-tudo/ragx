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

from ragx.clients.registry import (
    Client,
    Outcome,
    Result,
    _backup,
    _escrever,
    claude_settings,
)

EVENT = "SessionStart"

#: Reconhece a entrada do RAGX mesmo que o executável gravado mude de lugar.
_NOSSO = re.compile(r"ragx(\.exe)?\"?\s+claude\s+hint\s*$", re.IGNORECASE)


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


def _grupos(dados: dict[str, Any], path: Path, client: Client) -> tuple[list[Any] | None, Result | None]:
    hooks = dados.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        return None, Result(client, Outcome.FAILED, f"`hooks` em {path} não é um objeto — não vou mexer.")
    grupos = (hooks or {}).get(EVENT)
    if grupos is not None and not isinstance(grupos, list):
        return None, Result(client, Outcome.FAILED, f"`hooks.{EVENT}` em {path} não é uma lista — não vou mexer.")
    return list(grupos or []), None


def _sem_o_nosso(grupos: list[Any]) -> list[Any]:
    """Tira só a nossa entrada; grupo que ficar vazio sai junto."""
    out: list[Any] = []
    for grupo in grupos:
        if not isinstance(grupo, dict) or not isinstance(grupo.get("hooks"), list):
            out.append(grupo)
            continue
        resto = [h for h in grupo["hooks"] if not _eh_nosso(h)]
        if len(resto) == len(grupo["hooks"]):
            out.append(grupo)
        elif resto:
            out.append({**grupo, "hooks": resto})
    return out


def _gravar(path: Path, dados: dict[str, Any], grupos: list[Any], existia: bool) -> Path | None:
    hooks = dict(dados.get("hooks") or {})
    if grupos:
        hooks[EVENT] = grupos
    else:
        hooks.pop(EVENT, None)
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


# ── o texto ─────────────────────────────────────────────────────────────
_FERRAMENTAS = "select:mcp__ragx__search_hybrid,mcp__ragx__build_context,mcp__ragx__get_chunk"


def hint_text(start: Path | None = None) -> str:
    """O que o agente lê no início da sessão. Vazio fora de projeto RAGX.

    Usa a MESMA resolução do servidor MCP (`load_config` + `db_path`): uma dica
    que diz "indexado" onde o servidor responde `not_indexed` seria pior do que
    nenhuma.
    """
    from ragx.config import load_config

    cfg = load_config(start)
    if cfg.db_path.exists():
        return _texto_projeto(cfg)
    return _texto_pasta_pai(cfg)


def record_session_start(start: Path | None = None) -> None:
    """Uma sessão do Claude Code abriu num projeto indexado: vira evento na tela de atividade.

    Só quando o próprio Claude Code roda o hook (a origem diz qual perfil e qual
    sessão); rodar `ragx claude hint` à mão no terminal não é início de sessão.
    """
    from ragx.clients.registry import claude_origin
    from ragx.config import load_config
    from ragx.diagnostics import log_cli_call
    from ragx.storage.db import utcnow

    if not claude_origin():
        return
    cfg = load_config(start)
    if not cfg.db_path.exists():
        return
    log_cli_call(cfg.state_dir, {
        "ts": utcnow(),
        "command": "session_start",
        "project": cfg.project.name or cfg.root.name,
    })


def _status(cfg: Any) -> dict[str, Any]:
    try:
        dados = json.loads((cfg.state_dir / "status.json").read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _texto_projeto(cfg: Any) -> str:
    st = _status(cfg)
    nome = cfg.project.name or cfg.root.name
    docs = (st.get("counts") or {}).get("documents")
    idx = st.get("index") or {}
    partes = [f"{docs} documentos" if isinstance(docs, int) else None]
    if idx.get("finished_at"):
        quando = str(idx["finished_at"]).replace("T", " ").removesuffix("Z")
        branch = f", branch {idx['branch']}" if idx.get("branch") else ""
        partes.append(f"índice de {quando} UTC{branch}")
    resumo = ", ".join(p for p in partes if p)
    rodando = " Uma indexação está em andamento agora." if st.get("running") else ""
    # Regra, não sugestão. A primeira versão dizia "Grep continua certo quando
    # você já sabe o símbolo", e o agente, que sempre acha que sabe
    # (`AddJwtBearer` num projeto .NET), usou a brecha em toda pergunta.
    return (
        f"RAGX: este projeto ({nome}) está indexado pelo RAGX"
        f"{' (' + resumo + ')' if resumo else ''}. O índice se atualiza sozinho a cada "
        f"commit, checkout e merge.{rodando}\n\n"
        "REGRA DESTE PROJETO: para qualquer pergunta ou tarefa que exija entender ou "
        "localizar código (\"onde\", \"como funciona\", \"o que chama o quê\", antes de "
        "implementar ou corrigir), a PRIMEIRA ferramenta é o RAGX, não Grep/Glob/Read:\n"
        "1. mcp__ragx__build_context(query, tokens=3000): devolve os trechos relevantes, "
        "com arquivo e linhas, dentro de um orçamento de tokens. Na maioria das vezes "
        "já responde a pergunta;\n"
        "2. mcp__ragx__search_hybrid(query) quando quiser só a lista de onde algo está;\n"
        "3. só então Read/Grep, nos arquivos que o RAGX apontou, para confirmar ou "
        "aprofundar.\n"
        f'Se as ferramentas aparecerem só pelo nome (deferred), carregue antes: ToolSearch "{_FERRAMENTAS}".\n'
        "Pule o RAGX só quando a tarefa já traz o caminho exato do arquivo a abrir. "
        "Mudanças não commitadas podem não estar no índice: se editou algo nesta sessão "
        "e precisa buscá-lo, chame mcp__ragx__refresh antes."
    )


def _texto_pasta_pai(cfg: Any) -> str:
    """Sessão aberta ACIMA dos projetos (ex.: um monorepo com front e back
    indexados em separado). O servidor responde `not_indexed` para `current`,
    mas alcança cada projeto por `scope="project:<nome>"`."""
    try:
        registro = json.loads((cfg.hub_dir / "registry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    raiz = cfg.root.resolve()
    abaixo: list[tuple[str, str]] = []
    for p in (registro or {}).get("projects") or []:
        try:
            caminho = Path(str(p.get("path"))).resolve()
        except (OSError, ValueError):
            continue
        if caminho != raiz and caminho.is_relative_to(raiz) and (caminho / ".ragx" / "knowledge.db").exists():
            abaixo.append((str(p.get("name")), caminho.relative_to(raiz).as_posix()))
    if not abaixo:
        return ""
    lista = "\n".join(f'- {pasta}: scope="project:{nome}"' for nome, pasta in sorted(abaixo, key=lambda x: x[1]))
    return (
        "RAGX: esta pasta não tem índice próprio, mas contém projetos indexados pelo RAGX:\n"
        f"{lista}\n\n"
        "REGRA DESTA PASTA: para qualquer pergunta ou tarefa que exija entender ou "
        "localizar código, a PRIMEIRA ferramenta é o RAGX, não Grep/Glob/Read, passando "
        'o scope do projeto certo (ou scope="all" para buscar em todos):\n'
        "1. mcp__ragx__build_context(query, tokens=3000, scope=...): os trechos "
        "relevantes, com arquivo e linhas;\n"
        "2. mcp__ragx__search_hybrid(query, scope=...) para só localizar;\n"
        "3. só então Read/Grep, nos arquivos apontados.\n"
        f'Se as ferramentas aparecerem só pelo nome (deferred), carregue antes: ToolSearch "{_FERRAMENTAS}".'
    )
