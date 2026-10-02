"""Fila de arquivos tocados: o que o Claude editou e o índice ainda não viu.

Edição não commitada nunca entrava no índice por conta própria: só os hooks de git (commit,
checkout, merge) existiam, e o único caminho manual era o `refresh`, que custava de 26 a 91 s.
O hook `PostToolUse` do Claude Code só ENFILEIRA o caminho editado aqui (uma linha anexada a
`.ragx/touch.queue`: o custo é de milissegundos) e quem consome é `drain`, que chama
`index_paths` (RAGX-0140) só nos arquivos tocados. O servidor MCP drena antes de buscar.

Este módulo é só stdlib no topo (o hook roda a cada edição) e NUNCA lê o conteúdo de um
arquivo do projeto: só nomes. O que entra no índice passa pelo Security Gate dentro de
`index_paths`, como qualquer outro arquivo.

Formato: `touch.queue`, uma linha por caminho relativo POSIX. `enqueue` é um único `os.write`
em `O_APPEND` (atômico para linhas curtas); `claim` toma o lote inteiro por `os.replace`, a
mesma técnica atômica de `lock.mark_pending`: dois consumidores concorrentes nunca recebem o
mesmo caminho.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

QUEUE_NAME = "touch.queue"
_CLAIMED_SUFFIX = ".claimed"
#: Teto de caminhos por lote, quando a configuração não diz outro (`[watch] max_batch`).
DEFAULT_MAX_BATCH = 500
#: Uma linha muito comprida não é um caminho de arquivo: descarta em vez de gravar lixo.
_MAX_LINE = 1024


def queue_path(state_dir: Path) -> Path:
    return Path(state_dir) / QUEUE_NAME


def _chave(rel: str) -> str:
    """Chave de comparação: no Windows o sistema de arquivos não distingue maiúsculas."""
    return rel.lower() if sys.platform == "win32" else rel


def resolve(root: Path, path: str | os.PathLike[str]) -> str | None:
    """Caminho (absoluto ou relativo) -> relativo POSIX à raiz, ou `None` se escapar dela.

    Recusa `..` que sai da raiz, outra raiz, e symlink ou junction cujo destino fica fora (a
    ameaça A8, a mesma da varredura). A comparação ignora maiúsculas no Windows. O relativo
    devolvido NÃO é o caminho resolvido: é o que o usuário escreveu, normalizado, para casar
    com a chave que a varredura grava em `documents.rel_path`.
    """
    try:
        raiz = Path(os.path.abspath(root))
        bruto = Path(path)
        absoluto = Path(os.path.abspath(bruto if bruto.is_absolute() else raiz / bruto))
        rel = os.path.relpath(absoluto, raiz)
    except (OSError, ValueError):  # ValueError: outra unidade no Windows
        return None
    partes = Path(rel).parts
    if rel == "." or not partes or partes[0] == "..":
        return None
    # `normcase` por segmento resolve maiúsculas no Windows sem estragar o caminho devolvido
    if os.path.normcase(str(absoluto)) != os.path.normcase(str(raiz / rel)):
        return None
    try:
        real = Path(os.path.realpath(absoluto))
        real_raiz = Path(os.path.realpath(raiz))
        if os.path.relpath(real, real_raiz).split(os.sep, 1)[0] == "..":
            return None
    except (OSError, ValueError):
        return None
    return "/".join(partes)


def enqueue(state_dir: Path, rel_paths: Iterable[str]) -> int:
    """Anexa caminhos relativos à fila, num único `write`. Devolve quantos entraram."""
    linhas = []
    for rel in rel_paths:
        texto = rel.replace("\\", "/").strip()
        if texto and "\n" not in texto and "\r" not in texto and len(texto) <= _MAX_LINE:
            linhas.append(texto)
    if not linhas:
        return 0
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    dados = ("\n".join(linhas) + "\n").encode("utf-8")
    fd = os.open(queue_path(state_dir), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, dados)
    finally:
        os.close(fd)
    return len(linhas)


def _texto(path: Path) -> str:
    """O ÚNICO ponto que lê um arquivo aqui, e só da própria fila (nomes de caminho, nunca conteúdo do projeto)."""
    return path.read_text(encoding="utf-8", errors="replace")


def _ler(path: Path) -> list[str]:
    try:
        texto = _texto(path)
    except OSError:
        return []
    return _linhas(texto)


def _linhas(texto: str) -> list[str]:
    vistos: dict[str, str] = {}
    for linha in texto.splitlines():  # splitlines trata CRLF
        rel = linha.strip().replace("\\", "/")
        if rel and _chave(rel) not in vistos:
            vistos[_chave(rel)] = rel
    return list(vistos.values())


def pending(state_dir: Path) -> list[str]:
    """Os caminhos na fila, deduplicados, SEM consumi-los."""
    return _ler(queue_path(state_dir))


def is_pending(state_dir: Path) -> bool:
    try:
        return queue_path(state_dir).stat().st_size > 0
    except OSError:
        return False


@dataclass
class Claim:
    """Um lote tomado da fila. `done()` o descarta; `give_back()` o devolve à fila."""

    state_dir: Path
    paths: list[str]
    _file: Path | None = None

    def done(self) -> None:
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.unlink()
            self._file = None

    def give_back(self) -> None:
        enqueue(self.state_dir, self.paths)
        self.done()


def _ler_tomada(path: Path) -> str | None:
    """O texto do arquivo tomado, com algumas tentativas; `None` se continua ilegível."""
    for tentativa in range(5):
        try:
            return _texto(path)
        except OSError:
            time.sleep(0.01 * (tentativa + 1))
    return None


def _devolver_arquivo(tomada: Path, fila: Path) -> None:
    """Põe o arquivo tomado de volta como fila, sem pisar numa fila que já recomeçou; senão o deixa onde está."""
    try:
        os.link(tomada, fila)  # falha se a fila já existe: nunca sobrescreve
    except OSError:
        return  # fila nova no caminho (ou sem link físico): o arquivo tomado fica para recuperação, não é apagado
    with contextlib.suppress(OSError):
        tomada.unlink()


def claim(state_dir: Path, max_batch: int = DEFAULT_MAX_BATCH) -> Claim | None:
    """Toma a fila inteira, de forma atômica. `None` se estava vazia.

    O que passar do teto de `max_batch` volta para a fila: o lote seguinte o pega.
    """
    fila = queue_path(state_dir)
    tomada = Path(state_dir) / f"{QUEUE_NAME}.{os.getpid()}.{uuid4().hex}{_CLAIMED_SUFFIX}"
    try:
        os.replace(fila, tomada)
    except OSError:  # não existe (ou outro consumidor chegou primeiro)
        return None
    texto = _ler_tomada(tomada)
    if texto is None:
        # NÃO deu para ler (antivírus, outro processo segurando o arquivo): isso não é "fila vazia". Apagar aqui
        # perderia as edições da fila e o índice ficaria velho sem ninguém saber; devolve o arquivo à fila.
        _devolver_arquivo(tomada, fila)
        return None
    caminhos = _linhas(texto)
    if not caminhos:
        with contextlib.suppress(OSError):
            tomada.unlink()
        return None
    sobra = caminhos[max_batch:]
    if sobra:
        enqueue(state_dir, sobra)
    return Claim(Path(state_dir), caminhos[:max_batch], tomada)


@dataclass
class DrainResult:
    paths: int = 0
    indexed: bool = False
    busy: bool = False
    error: str | None = None
    #: o grafo não conseguiu acompanhar (RAGX-0151); a indexação concluiu e o lote NÃO volta à fila
    graph_warning: str | None = None


def drain(cfg: Any, source: str = "touch", wait_ms: int | None = None) -> DrainResult:
    """Espera o debounce, toma a fila e reindexa SÓ esses arquivos (`index_paths`).

    NÃO pega `index.lock` aqui: `index_paths` já o pega e, com a trava ocupada, marca o pedido
    como pendente e levanta `IndexBusyError`; pegar duas vezes travaria a própria chamada. Em
    `IndexBusyError` ou falha o lote volta à fila (o dono refaz a passada incremental ao
    terminar, e ela vê os arquivos novos por tamanho e `mtime`).
    """
    espera = cfg.watch.touch_debounce_ms if wait_ms is None else wait_ms
    if espera > 0:
        time.sleep(espera / 1000)
    lote = claim(cfg.state_dir, cfg.watch.max_batch)
    if lote is None:
        return DrainResult()
    from ragx.core.errors import IndexBusyError
    from ragx.indexing.pipeline import index_paths

    resultado = DrainResult(paths=len(lote.paths))
    try:
        relatorio = index_paths(cfg, lote.paths, source=source)
    except IndexBusyError:
        lote.give_back()
        resultado.busy = True
        return resultado
    except Exception as exc:  # um erro aqui nunca pode derrubar quem chamou (hook, servidor)
        lote.give_back()
        resultado.error = f"{type(exc).__name__}: {exc}"
        return resultado
    lote.done()
    resultado.indexed = True
    if relatorio.touched_documents:
        try:
            from ragx.graph.service import update_documents

            update_documents(cfg, relatorio.touched_documents)
        except Exception as exc:  # o grafo nunca derruba a indexação que já deu certo
            resultado.graph_warning = f"{type(exc).__name__}: {exc}"
    return resultado


def visible(cfg: Any, paths: list[str]) -> list[str]:
    """Só os caminhos que o Security Gate admitiria PELO NOME.

    A fila aceita qualquer caminho dentro da raiz, inclusive `.env`; listá-lo numa resposta de
    busca revelaria que o arquivo existe. Quem passa por aqui nunca expõe o que o gate bloqueia
    ou ignora. Só decide pelo nome: nenhum byte do arquivo é lido.
    """
    if not paths:
        return []
    from ragx.core.models import Verdict
    from ragx.security.gate import SecurityGate

    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    return [p for p in paths if gate.admit(p).verdict is Verdict.ALLOW]


def settle(cfg: Any, source: str = "mcp:touch", can_drain: bool = True) -> list[str]:
    """Antes de uma busca: reindexa o que está na fila e devolve o que AINDA ficou para trás.

    Sem fila é só um `stat`. Sem espera de debounce (quem busca já está esperando) e sem nunca
    levantar: o que sobrar (índice ocupado, falha) volta na lista, e a resposta da busca diz
    quais caminhos podem estar desatualizados em vez de fingir que está tudo em dia. Com
    `can_drain=False` (servidor somente leitura) NÃO escreve no índice: só informa o que falta.
    """
    if not is_pending(cfg.state_dir):
        return []
    if can_drain:
        drain(cfg, source=source, wait_ms=0)
    return visible(cfg, pending(cfg.state_dir))


def spawn_drain(root: Path) -> None:
    """Dispara a drenagem DESTACADA: o hook não pode esperar a indexação.

    Mesma técnica de `githooks.spawn_index`: no Windows, `CREATE_NO_WINDOW` (sem console,
    cada `git` filho ganharia uma janela) com `NEW_PROCESS_GROUP`; fora dele, sessão nova. O
    interpretador é o MESMO que está rodando (`sys.executable`), nunca um `ragx` procurado no
    PATH, que poderia ser outra instalação.
    """
    argv = [sys.executable, "-m", "ragx.cli.main", "touch", "--drain", "--root", str(root)]
    logs = Path(root) / ".ragx" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "hooks.log").open("a", encoding="utf-8") as log:
        kwargs: dict[str, Any] = {
            "cwd": root, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log,
        }
        if sys.platform == "win32":
            detached = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | NEW_PROCESS_GROUP
            try:
                subprocess.Popen(argv, creationflags=detached | 0x01000000, **kwargs)
            except OSError:
                subprocess.Popen(argv, creationflags=detached, **kwargs)
        else:
            subprocess.Popen(argv, start_new_session=True, **kwargs)
