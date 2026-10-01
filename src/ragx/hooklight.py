"""Entrada leve dos hooks que rodam em TODA sessão e TODO commit (RAGX-0143).

`ragx claude hint` (o `SessionStart` do Claude Code, que roda até em subagente) levava 481 a 659 ms,
e o hook de git bloqueava o commit por 539 a 1.041 ms, contra 41 a 56 ms de um Python vazio. A causa:
o ponto de entrada importava typer, rich, pydantic e 25 módulos de comando antes de olhar o primeiro
argumento. Este módulo faz o trabalho desses dois caminhos usando SÓ a stdlib (e `ragx.origin`,
`ragx.diagnostics`, que também são stdlib), e `ragx.entry` despacha para ele antes de importar a CLI.

Regras:

- Só stdlib. Importar este módulo não carrega typer, rich, pydantic, numpy, yaml, pathspec nem
  `ragx.config`/`ragx.core`/`ragx.storage`/`ragx.clients` (um teste confere num subprocesso).
- Lê só artefatos próprios do RAGX: `ragx.toml`, `.ragx/status.json` e o `registry.json` do hub.
  Nunca o conteúdo de um arquivo do projeto, e não percorre diretório (o teste arquitetural proíbe
  `read_bytes`, `rglob`, `walk`, `scandir`, `iterdir` e `glob` aqui).
- Nunca falha: erro em qualquer ponto vira silêncio e código 0, porque um erro aqui atrasaria ou
  sujaria o início de toda sessão e todo commit, em qualquer pasta.

O texto da dica tem UMA fonte, esta: `ragx.clients.claude_hint.hint_text` delega para cá.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

CONFIG_NAME = "ragx.toml"
EVENTS = ("post-checkout", "post-commit", "post-merge")

FERRAMENTAS = "select:mcp__ragx__search_hybrid,mcp__ragx__build_context,mcp__ragx__get_chunk"


# ── configuração mínima ─────────────────────────────────────────────────
def find_root(start: Path | None = None) -> tuple[Path, bool]:
    """Sobe do cwd até achar `ragx.toml`. Sem ele, usa o cwd (como `ragx.config.find_root`)."""
    cur = Path(start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / CONFIG_NAME).is_file():
            return candidate, True
    return cur, False


def _toml(path: Path) -> dict[str, Any]:
    dados = tomllib.loads(path.read_text(encoding="utf-8"))
    return dados if isinstance(dados, dict) else {}


def _secao(dados: dict[str, Any], nome: str) -> dict[str, Any]:
    valor = dados.get(nome)
    return valor if isinstance(valor, dict) else {}


class Leve:
    """O que a dica precisa da configuração: raiz, nome do projeto e pasta do hub."""

    __slots__ = ("hub_dir", "nome", "root")

    def __init__(self, root: Path, nome: str, hub_dir: Path):
        self.root = root
        self.nome = nome
        self.hub_dir = hub_dir

    @property
    def state_dir(self) -> Path:
        return self.root / ".ragx"

    @property
    def db_path(self) -> Path:
        return self.state_dir / "knowledge.db"


def carregar(start: Path | None = None) -> Leve:
    """Mesma precedência de `ragx.config.load_config` para os dois campos que a dica usa:
    `RAGX_*` > `ragx.toml` > config do usuário > padrão (`projeto`, `~/.ragx/hub`)."""
    root, found = find_root(start)
    projeto: dict[str, Any] = {}
    hub: dict[str, Any] = {}
    usuario = Path(os.path.expanduser("~/.config/ragx/config.toml"))
    for arquivo, existe in ((usuario, usuario.is_file()), (root / CONFIG_NAME, found)):
        if existe:
            dados = _toml(arquivo)
            projeto = {**projeto, **_secao(dados, "project")}
            hub = {**hub, **_secao(dados, "hub")}
    nome = os.environ.get("RAGX_PROJECT_NAME", projeto.get("name", "projeto"))
    hub_path = os.environ.get("RAGX_HUB_PATH", hub.get("path", "~/.ragx/hub"))
    return Leve(root, str(nome) or root.name, Path(os.path.expanduser(str(hub_path))))


# ── o texto ─────────────────────────────────────────────────────────────
def hint_text(start: Path | None = None) -> str:
    """O que o agente lê no início da sessão. Vazio fora de projeto RAGX.

    A mesma resolução do servidor MCP (`ragx.toml` + `db_path`): uma dica que diz "indexado"
    onde o servidor responde `not_indexed` seria pior do que nenhuma.
    """
    cfg = carregar(start)
    if cfg.db_path.exists():
        return texto_projeto(cfg)
    return texto_pasta_pai(cfg)


def _status(cfg: Any) -> dict[str, Any]:
    try:
        dados = json.loads((cfg.state_dir / "status.json").read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def texto_projeto(cfg: Any) -> str:
    st = _status(cfg)
    nome = cfg.nome
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
        f'Se as ferramentas aparecerem só pelo nome (deferred), carregue antes: ToolSearch "{FERRAMENTAS}".\n'
        "Pule o RAGX só quando a tarefa já traz o caminho exato do arquivo a abrir. "
        "Arquivos editados com Edit/Write entram no índice sozinhos; se a resposta trouxer "
        "`stale_paths`, ou se mexeu por shell ou outro editor, chame mcp__ragx__refresh antes."
    )


def texto_pasta_pai(cfg: Any) -> str:
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
        f'Se as ferramentas aparecerem só pelo nome (deferred), carregue antes: ToolSearch "{FERRAMENTAS}".'
    )


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def record_session_start(start: Path | None = None) -> None:
    """Uma sessão do Claude Code abriu num projeto indexado: vira evento na tela de atividade.

    Só quando o próprio Claude Code roda o hook (a origem diz qual perfil e qual sessão); rodar
    `ragx claude hint` à mão no terminal não é início de sessão.
    """
    from ragx.diagnostics import log_cli_call
    from ragx.origin import claude_origin

    if not claude_origin():
        return
    cfg = carregar(start)
    if not cfg.db_path.exists():
        return
    log_cli_call(cfg.state_dir, {
        "ts": _utcnow(),
        "command": "session_start",
        "project": cfg.nome or cfg.root.name,
    })


def run_hint() -> int:
    """`ragx claude hint`. Nunca falha e nunca escreve nada se der erro."""
    try:
        texto = hint_text()
        record_session_start()
    except Exception:
        return 0
    if texto:
        # Direto no stdout, sem Rich: o texto vai para o contexto do agente. Bytes UTF-8: no
        # Windows, stdout em pipe sai em cp1252 e os acentos chegariam ao agente como lixo.
        dados = (texto + "\n").encode("utf-8")
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            sys.stdout.flush()
            buffer.write(dados)
            buffer.flush()
        else:
            sys.stdout.write(texto + "\n")
    return 0


# ── o aviso de edição (`ragx touch --stdin-json`) ────────────────────────
#: Campos do `tool_input` do hook `PostToolUse` que carregam o caminho editado.
CAMPOS_DE_CAMINHO = ("file_path", "notebook_path", "path")


def ler_stdin() -> list[str]:
    """Os caminhos editados que o hook descreve no stdin. Entrada lixo vira lista vazia."""
    try:
        buffer = getattr(sys.stdin, "buffer", None)
        bruto = buffer.read().decode("utf-8", errors="replace") if buffer else sys.stdin.read()
        dados: Any = json.loads(bruto)
    except Exception:
        return []
    if not isinstance(dados, dict):
        return []
    entrada = dados.get("tool_input")
    if not isinstance(entrada, dict):
        return []
    return [str(entrada[c]) for c in CAMPOS_DE_CAMINHO if isinstance(entrada.get(c), str) and entrada[c]]


def run_touch() -> int:
    """`ragx touch --stdin-json`: enfileira o arquivo editado e dispara a drenagem. Sempre 0.

    A raiz vem do ARQUIVO editado (a sessão pode estar numa pasta-pai com vários projetos), pasta
    sem índice é ignorada, e nada é lido do projeto: só nomes (`ragx.indexing.touchq`).
    """
    try:
        from ragx.indexing import touchq

        por_raiz: dict[Path, list[str]] = {}
        for bruto in ler_stdin():
            arquivo = Path(bruto).expanduser()
            if not arquivo.is_absolute():
                arquivo = Path.cwd() / arquivo
            raiz, achou = find_root(arquivo.parent)
            if achou:
                por_raiz.setdefault(raiz, []).append(str(arquivo))
        for raiz, arquivos in por_raiz.items():
            state_dir = raiz / ".ragx"
            if not (state_dir / "knowledge.db").exists():
                continue  # projeto sem índice: nada a atualizar
            rels = [r for a in arquivos if (r := touchq.resolve(raiz, a)) is not None]
            rels = [r for r in rels if r != ".ragx" and not r.startswith(".ragx/")]
            if rels and touchq.enqueue(state_dir, rels):
                touchq.spawn_drain(raiz)
    except Exception:
        pass
    return 0


# ── hooks de git ────────────────────────────────────────────────────────
def should_run(event: str, args: list[str]) -> bool:
    if event == "post-checkout":
        # args: HEAD anterior, HEAD novo, flag (1 = troca de branch, 0 = arquivo)
        return len(args) >= 3 and args[2] == "1"
    return event in EVENTS


def index_argv(root: Path, event: str) -> list[str]:
    # NUNCA `shutil.which("ragx")` aqui: isso resolve o PATH de NOVO, no
    # momento do spawn, e pode achar uma instalação diferente da que rodou
    # `hook-run` (reproduzido: entrada de PATH velha apontando para um `ragx`
    # sem `--source`, indexação nunca atualizava, log só dizia "No such
    # option: --source"). `sys.executable` é o MESMO interpretador que já
    # está rodando este processo — sempre correto, sem lookup nenhum. A indexação em si
    # segue pela CLI completa (`-m ragx.cli.main`).
    return [
        sys.executable, "-m", "ragx.cli.main",
        "index", str(root), "--quiet", "--source", f"hook:{event}",
    ]


def spawn_index(root: Path, event: str) -> None:
    logs = root / ".ragx" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = (logs / "hooks.log").open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "cwd": root, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log,
    }
    if sys.platform == "win32":
        # Git for Windows não tem nohup: o hook não pode esperar a indexação
        # inteira, então ela roda solta (NEW_PROCESS_GROUP + saída no log).
        # NÃO usar DETACHED_PROCESS: sem console, cada `git` que a indexação
        # roda ganha uma janela de terminal nova (piscava a cada commit).
        # CREATE_NO_WINDOW dá um console oculto, herdado pelos filhos.
        # BREAKAWAY_FROM_JOB pode ser negado pelo job pai; nesse caso tenta sem ele.
        detached = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | NEW_PROCESS_GROUP
        try:
            subprocess.Popen(index_argv(root, event),
                             creationflags=detached | 0x01000000, **kwargs)
        except OSError:
            subprocess.Popen(index_argv(root, event), creationflags=detached, **kwargs)
    else:
        subprocess.Popen(index_argv(root, event), start_new_session=True, **kwargs)
    log.close()


def parse_hook_run(argv: list[str]) -> tuple[str, Path, list[str]] | None:
    """`hook-run EVENT --root R [ARGS...]` -> (evento, raiz, args). `None` se não for esse formato.

    O que não casa (sem `--root`, opção desconhecida antes dos argumentos) volta `None` e vai para
    a CLI completa, que dá a mesma mensagem de erro de sempre.
    """
    evento: str | None = None
    raiz: Path | None = None
    args: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            raiz = Path(argv[i + 1])
            i += 2
            continue
        if a.startswith("--root="):
            raiz = Path(a[len("--root="):])
        elif evento is None:
            evento = a
        else:
            args.append(a)
        i += 1
    if evento is None or raiz is None:
        return None
    return evento, raiz, args


def run_hook(argv: list[str]) -> int:
    """`ragx hook-run`: dispara a indexação destacada e devolve o terminal. Sempre 0."""
    analisado = parse_hook_run(argv)
    if analisado is None:
        return 0
    evento, raiz, args = analisado
    try:
        if evento in EVENTS and should_run(evento, args) and (raiz / CONFIG_NAME).exists():
            spawn_index(raiz, evento)
    except Exception:
        pass  # o hook de git roda com `|| true`; falhar aqui nunca pode atrapalhar o commit
    return 0
