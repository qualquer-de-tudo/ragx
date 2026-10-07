"""Entrada leve dos hooks que rodam em TODA sessão e TODO commit (RAGX-0143).

`ragx claude hint` (a dica do Claude Code em `SessionStart` e `SubagentStart`) levava 481 a 659 ms,
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

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
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

    __slots__ = ("hub_dir", "nome", "retain_days", "root")

    def __init__(self, root: Path, nome: str, hub_dir: Path, retain_days: int = 14):
        self.root = root
        self.nome = nome
        self.hub_dir = hub_dir
        self.retain_days = retain_days

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
    log: dict[str, Any] = {}
    usuario = Path(os.path.expanduser("~/.config/ragx/config.toml"))
    for arquivo, existe in ((usuario, usuario.is_file()), (root / CONFIG_NAME, found)):
        if existe:
            dados = _toml(arquivo)
            projeto = {**projeto, **_secao(dados, "project")}
            hub = {**hub, **_secao(dados, "hub")}
            log = {**log, **_secao(dados, "log")}
    nome = os.environ.get("RAGX_PROJECT_NAME", projeto.get("name", "projeto"))
    hub_path = os.environ.get("RAGX_HUB_PATH", hub.get("path", "~/.ragx/hub"))
    dias = log.get("retain_days", 14)
    retain_days = dias if isinstance(dias, int) and not isinstance(dias, bool) else 14
    return Leve(root, str(nome) or root.name, Path(os.path.expanduser(str(hub_path))), retain_days)


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


def texto_projeto(cfg: Any) -> str:
    """O que o agente lê ao abrir uma sessão num projeto indexado: a regra e as três ferramentas.

    Curto de propósito (~100 tokens, era ~285): roda em toda sessão. Sai o resumo de documentos, data e
    branch do índice (o frescor volta onde importa: `stale_paths` na busca) e o aviso sobre `refresh`.
    A primeira versão deixava uma brecha ("Grep continua certo quando você já sabe o símbolo") e o
    agente, que sempre acha que sabe, a usou em toda pergunta: por isso é regra, não sugestão.
    """
    return (
        f"RAGX: projeto {cfg.nome} indexado. Para \"onde está\", \"como funciona\", "
        "\"o que chama o quê\", use o RAGX ANTES de Grep/Glob/Read:\n"
        "- mcp__ragx__build_context(query): monta o contexto da tarefa;\n"
        "- mcp__ragx__search_hybrid(query): localiza;\n"
        "- mcp__ragx__get_chunk(id): abre um trecho.\n"
        f'Se as ferramentas aparecerem só pelo nome, carregue: ToolSearch "{FERRAMENTAS}".'
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
        f"RAGX: esta pasta contém projetos indexados:\n{lista}\n"
        "Para entender ou localizar código, use o RAGX ANTES de Grep/Glob/Read, com o scope do projeto "
        '(ou scope="all"): mcp__ragx__build_context(query, scope), mcp__ragx__search_hybrid(query, scope), '
        "mcp__ragx__get_chunk(id).\n"
        f'Se as ferramentas aparecerem só pelo nome, carregue: ToolSearch "{FERRAMENTAS}".'
    )


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ler_json(espera_s: float = 0.5) -> dict[str, Any]:
    """O JSON que o Claude Code entrega no stdin do hook, ou `{}`.

    Nunca bloqueia: com o stdin num terminal (uso manual de `ragx claude hint`) nem tenta, e com um pipe
    que não fecha desiste depois de `espera_s`. Entrada inválida ou que não é um objeto vira `{}`.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
    except Exception:
        return {}
    resultado: list[Any] = []

    def ler() -> None:
        try:
            buffer = getattr(sys.stdin, "buffer", None)
            bruto = buffer.read().decode("utf-8", errors="replace") if buffer else sys.stdin.read()
            resultado.append(json.loads(bruto))
        except Exception:
            pass

    fio = threading.Thread(target=ler, daemon=True)
    fio.start()
    fio.join(espera_s)
    dados = resultado[0] if resultado else {}
    return dados if isinstance(dados, dict) else {}


#: Reinício de contexto ou retomada de sessão longa: renova a orientação.
REENTREGA = ("clear", "compact", "resume")


def _sanear_sessao(valor: Any) -> str:
    """`session_id` vira nome de arquivo: só `[A-Za-z0-9_-]`, até 64 (nada de `..`, `\\`, `:`)."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(valor or ""))[:64]


def primeira_vez(pasta: Path, sessao: str, source: str | None) -> bool:
    """A dica desta sessão ainda não foi entregue? Marca a entrega, de forma atômica (`O_EXCL`).

    Sem `session_id` não há como saber: entrega (o uso manual segue igual). Depois de `clear` ou
    `compact` ou `resume` entrega de novo e renova o marcador. Qualquer erro de disco entrega: perder a dica é pior
    do que repeti-la.
    """
    if not sessao:
        return True
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        fd = os.open(pasta / sessao, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        if source in REENTREGA:
            with contextlib.suppress(OSError):
                os.utime(pasta / sessao)
            return True
        return False
    except OSError:
        return True
    os.close(fd)
    _podar_marcadores(pasta)
    return True


#: Marcador de sessão com mais de 7 dias não serve mais a ninguém.
MARCADOR_TTL_S = 7 * 24 * 3600


def _podar_marcadores(pasta: Path) -> None:
    """Apaga marcadores velhos desta pasta (a NOSSA, de cache: nunca uma pasta do projeto).

    É a única listagem de diretório deste módulo, e só da pasta de marcadores, ao criar um novo.
    """
    agora = time.time()
    with contextlib.suppress(OSError):
        for nome in os.listdir(pasta):
            arquivo = pasta / nome
            with contextlib.suppress(OSError):
                if agora - arquivo.stat().st_mtime > MARCADOR_TTL_S:
                    arquivo.unlink()


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
    }, cfg.retain_days)


def run_hint() -> int:
    """`ragx claude hint`. Nunca falha e nunca escreve nada se der erro.

    SessionStart usa um marcador por sessão, renovado em clear, compact e resume.
    SubagentStart devolve JSON com contexto para o filho, sem consumir o marcador do pai
    nem registrar outra sessão. O cwd do evento determina o projeto.
    """
    try:
        dados = _ler_json()
        cwd = dados.get("cwd")
        start = Path(cwd) if isinstance(cwd, str) and cwd else None
        cfg = carregar(start)
        indexado = cfg.db_path.exists()
        texto = texto_projeto(cfg) if indexado else texto_pasta_pai(cfg)
        if not texto:
            return 0
        if dados.get("hook_event_name") == "SubagentStart":
            # O Claude injeta esta saída no contexto do filho e deduplica por agente.
            # Não cria outra sessão nem consome o marcador do pai.
            texto = json.dumps({"hookSpecificOutput": {
                "hookEventName": "SubagentStart", "additionalContext": texto,
            }}, ensure_ascii=False)
            _emitir(texto)
            return 0
        pasta = (cfg.state_dir if indexado else cfg.hub_dir) / ("cache/hint" if indexado else "hint")
        if not primeira_vez(pasta, _sanear_sessao(dados.get("session_id")), dados.get("source")):
            return 0
        record_session_start(start)
    except Exception:
        return 0
    # Direto no stdout, sem Rich: o texto vai para o contexto do agente. Bytes UTF-8: no
    # Windows, stdout em pipe sai em cp1252 e os acentos chegariam ao agente como lixo.
    _emitir(texto)
    return 0


def _emitir(texto: str) -> None:
    """Saída UTF-8 para o contexto do Claude, inclusive em pipes no Windows."""
    dados_saida = (texto + "\n").encode("utf-8")
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout.flush()
        buffer.write(dados_saida)
        buffer.flush()
    else:
        sys.stdout.write(texto + "\n")


# ── o lembrete no Grep/Glob (`ragx claude nudge`, PreToolUse) ─────────────
def texto_lembrete() -> str:
    """O que o agente lê ao fazer o primeiro `Grep`/`Glob` da sessão: sugere, não manda, e é curto.

    Nunca ecoa o `tool_input`: o padrão buscado pode ser um segredo.
    """
    return (
        "RAGX: este projeto está indexado. Para entender ou localizar código, "
        "mcp__ragx__build_context(query) devolve os trechos relevantes, com arquivo e linhas, "
        "em geral mais barato do que Grep + Read."
    )


def run_nudge() -> int:
    """`ragx claude nudge`: no primeiro `Grep`/`Glob` da sessão, num projeto indexado, adiciona contexto.

    Sugere sem bloquear (bloquear `Grep`/`Read` está descartado) e cala em todo o resto: projeto sem
    índice, sessão que já foi avisada, stdin vazio ou inválido, qualquer erro. O marcador
    O marcador em `.ragx/cache/nudge/` é criado com `O_EXCL`: com vários `Grep` em paralelo
    só um imprime por agente. Filhos têm marcador próprio, derivado de session_id + agent_id.
    """
    try:
        dados = _ler_json()
        sessao = _sanear_sessao(dados.get("session_id"))
        cwd = dados.get("cwd")
        if not sessao or not isinstance(cwd, str) or not cwd:
            return 0
        cfg = carregar(Path(cwd))
        if not cfg.db_path.exists():
            return 0
        agente = _sanear_sessao(dados.get("agent_id"))
        marcador = hashlib.sha256(f"{sessao}:{agente}".encode()).hexdigest() if agente else sessao
        if not primeira_vez(cfg.state_dir / "cache" / "nudge", marcador, None):
            return 0
        from ragx.diagnostics import log_cli_call

        log_cli_call(cfg.state_dir, {
            "ts": _utcnow(), "command": "nudge", "project": cfg.nome or cfg.root.name,
        }, cfg.retain_days)
        saida = json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": texto_lembrete()}},
            ensure_ascii=False,
        )
    except Exception:
        return 0
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout.flush()
        buffer.write((saida + "\n").encode("utf-8"))
        buffer.flush()
    else:
        sys.stdout.write(saida + "\n")
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
