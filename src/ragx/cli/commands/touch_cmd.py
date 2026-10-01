"""`ragx touch` — o hook `PostToolUse` do Claude Code avisa que um arquivo foi editado.

O Claude Code roda este comando depois de cada `Edit`, `Write` ou `MultiEdit`, com um JSON no
stdin (`tool_input.file_path`). O comando só ENFILEIRA o caminho (`.ragx/touch.queue`) e dispara,
destacado, a drenagem que reindexa só os arquivos tocados (`index_paths`, RAGX-0140): o agente
não espera, e a próxima busca já vê a edição.

Sai SEMPRE com código 0, como `ragx claude hint`: um erro aqui sujaria ou atrasaria toda edição
do agente, em qualquer pasta, e a ausência do RAGX nunca é motivo para isso.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def touch(
    paths: Annotated[list[str] | None, typer.Argument(help="Arquivos editados (caminho absoluto ou relativo).")] = None,
    stdin_json: Annotated[
        bool, typer.Option("--stdin-json", help="Lê o JSON do hook `PostToolUse` no stdin.")
    ] = False,
    root: Annotated[Path | None, typer.Option("--root", help="Raiz do projeto (padrão: a do arquivo).")] = None,
    drain: Annotated[bool, typer.Option("--drain", hidden=True, help="Só drena a fila (uso interno).")] = False,
    no_drain: Annotated[bool, typer.Option("--no-drain", hidden=True)] = False,
) -> None:
    """Registra arquivos editados e reindexa só eles, sem o agente esperar."""
    try:
        _executar(paths or [], stdin_json, root, drain, no_drain)
    except Exception:
        return  # nunca falha: ver a docstring do módulo


def _executar(
    paths: list[str], stdin_json: bool, root: Path | None, drain: bool, no_drain: bool
) -> None:
    from ragx.config import find_root, load_config
    from ragx.hooklight import ler_stdin
    from ragx.indexing import touchq

    if drain:
        if root is not None:
            cfg = load_config(root)
            if cfg.db_path.exists():
                touchq.drain(cfg, source="touch")
        return

    candidatos = [*paths, *(ler_stdin() if stdin_json else [])]
    # agrupa por projeto: a raiz vem do ARQUIVO editado, não do cwd (a sessão pode estar numa
    # pasta-pai com vários projetos)
    por_raiz: dict[Path, list[str]] = {}
    for bruto in candidatos:
        arquivo = Path(bruto).expanduser()
        if not arquivo.is_absolute():
            arquivo = Path.cwd() / arquivo
        if root is not None:
            raiz, achou = Path(root).resolve(), True
        else:
            raiz, achou = find_root(arquivo.parent)
        if achou:
            por_raiz.setdefault(raiz, []).append(str(arquivo))

    for raiz, arquivos in por_raiz.items():
        cfg = load_config(raiz)
        if not cfg.db_path.exists():
            continue  # projeto sem índice: nada a atualizar
        rels = [r for a in arquivos if (r := touchq.resolve(raiz, a)) is not None]
        rels = [r for r in rels if r != ".ragx" and not r.startswith(".ragx/")]
        if rels and touchq.enqueue(cfg.state_dir, rels) and not no_drain:
            touchq.spawn_drain(raiz)
