"""Hooks de git que mantêm o índice na branch em que você está.

Cada hook ganha um bloco marcado por raiz de projeto, então convive com hooks
de outras ferramentas e com mais de um projeto RAGX no mesmo repositório. O
bloco chama `ragx hook-run`, que dispara a indexação destacada e devolve o
terminal na hora. Opt-out por RAGX_SKIP_HOOK=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ragx import gitinfo
from ragx.core.errors import UsageError

EVENTS = ("post-checkout", "post-commit", "post-merge")
_SHEBANG = "#!/bin/sh\n"
# `\` entra na lista porque, dentro de `--root "<valor>"` (aspas duplas), uma
# barra invertida no fim do valor escapa a aspa de fechamento e devolve o
# resto do arquivo de hook a um shell sem citação nenhuma. Já foi explorado de
# verdade: raiz terminada em `\` seguida de outro bloco com `;comando;` no
# valor executava o comando injetado.
_FORBIDDEN = ('"', "`", "$", "\\", "\n", "\r")

_CARACTERE_PERIGOSO = '(" ` $ \\ ou quebra de linha)'


def _recusar_se_perigoso(valor: str, mensagem: str) -> None:
    if any(c in valor for c in _FORBIDDEN):
        raise UsageError(mensagem)


def _key(root: Path) -> str:
    return root.resolve().as_posix()


def _markers(root: Path) -> tuple[str, str]:
    k = _key(root)
    return f"# ragx-hook-start {k}", f"# ragx-hook-end {k}"


def command_prefix() -> str:
    exe = shutil.which("ragx")
    candidate = Path(exe).as_posix() if exe else Path(sys.executable).as_posix()
    # Defesa em profundidade: `shutil.which`/`sys.executable` normalmente não
    # devolvem caminho perigoso, mas se devolvessem, o hook ficaria tão quebrado
    # quanto uma raiz de projeto perigosa (mesmo mecanismo de citação).
    _recusar_se_perigoso(
        candidate,
        "o caminho do executável do ragx tem caractere que o shell do hook "
        f"interpretaria {_CARACTERE_PERIGOSO}; reinstale o ragx em outro caminho",
    )
    if exe:
        return f'"{candidate}"'
    return f'"{candidate}" -m ragx.cli.main'


def _block(root: Path, event: str, prefix: str) -> str:
    start, end = _markers(root)
    return (
        f"{start}\n"
        'if [ "$RAGX_SKIP_HOOK" != "1" ]; then\n'
        f'  {prefix} hook-run {event} --root "{_key(root)}" "$@" >/dev/null 2>&1 || true\n'
        "fi\n"
        f"{end}\n"
    )


def _insert_block(body: str, root: Path, event: str, prefix: str) -> str:
    """Insere o bloco logo após a primeira linha (shebang), nunca no fim.

    Hook real de outra ferramenta costuma terminar com `exec` ou `exit` antes
    do fim do arquivo (pre-commit-framework, husky v9): um bloco anexado ao
    final nunca rodaria, mas `state()` continuaria dizendo `installed: true`.
    O bloco do RAGX é curto, autocontido e termina em `|| true`, então é
    seguro rodar primeiro.
    """
    block = _block(root, event, prefix)
    lines = body.splitlines(keepends=True)
    if not lines:
        return block
    head = lines[0] if lines[0].endswith("\n") else lines[0] + "\n"
    return head + block + "".join(lines[1:])


def _strip(text: str, root: Path) -> str:
    start, end = _markers(root)
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        s = line.rstrip("\r\n")
        if s == start:
            skipping = True
            continue
        if skipping and s == end:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "".join(out)


def _dir_or_error(root: Path) -> Path:
    d = gitinfo.hooks_dir(root)
    if d is None:
        raise UsageError(f"{root} não está dentro de um repositório git")
    return d


def install(root: Path, prefix: str | None = None) -> list[Path]:
    key = _key(root)
    _recusar_se_perigoso(
        key,
        "o caminho do projeto tem caractere que o shell do hook interpretaria "
        f"{_CARACTERE_PERIGOSO}; mova o projeto para instalar hooks",
    )
    d = _dir_or_error(root)
    d.mkdir(parents=True, exist_ok=True)
    prefix = prefix or command_prefix()
    written: list[Path] = []
    for event in EVENTS:
        path = d / event
        if path.exists():
            try:
                current = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise UsageError(
                    f"não foi possível ler o hook existente {path}: {exc}"
                ) from exc
        else:
            current = _SHEBANG
        body = _strip(current, root)
        path.write_text(
            _insert_block(body, root, event, prefix), encoding="utf-8", newline="\n"
        )
        if os.name != "nt":
            path.chmod(0o755)
        written.append(path)
    _refresh_status(root)
    return written


def uninstall(root: Path) -> list[Path]:
    d = _dir_or_error(root)
    touched: list[Path] = []
    for event in EVENTS:
        path = d / event
        if not path.exists():
            continue
        current = path.read_text(encoding="utf-8")
        body = _strip(current, root)
        if body == current:
            continue
        if body.strip() in ("", _SHEBANG.strip()):
            path.unlink()
        else:
            path.write_text(body, encoding="utf-8", newline="\n")
        touched.append(path)
    _refresh_status(root)
    return touched


def state(root: Path) -> dict[str, Any]:
    d = gitinfo.hooks_dir(root)
    start, _ = _markers(root)
    events: dict[str, bool] = {}
    for event in EVENTS:
        path = d / event if d else None
        # Comparação por LINHA inteira, não substring: o marcador de uma raiz
        # que é prefixo de outra (`.../api` vs `.../api-gateway`) senão bate
        # por engano dentro da linha da raiz mais longa.
        events[event] = bool(
            path
            and path.exists()
            and start in path.read_text(encoding="utf-8").splitlines()
        )
    return {
        "hooks_dir": d.as_posix() if d else None,
        "events": events,
        "installed": bool(d) and all(events.values()),
    }


def installed(root: Path) -> bool | None:
    if gitinfo.hooks_dir(root) is None:
        return None
    return bool(state(root)["installed"])


def should_run(event: str, args: list[str]) -> bool:
    if event == "post-checkout":
        # args: HEAD anterior, HEAD novo, flag (1 = troca de branch, 0 = arquivo)
        return len(args) >= 3 and args[2] == "1"
    return event in EVENTS


def _index_argv(root: Path, event: str) -> list[str]:
    # NUNCA `shutil.which("ragx")` aqui: isso resolve o PATH de NOVO, no
    # momento do spawn, e pode achar uma instalação diferente da que rodou
    # `hook-run` (reproduzido: entrada de PATH velha apontando para um `ragx`
    # sem `--source`, indexação nunca atualizava, log só dizia "No such
    # option: --source"). `sys.executable` é o MESMO interpretador que já
    # está rodando este processo — sempre correto, sem lookup nenhum.
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
        # Git for Windows não tem nohup: sem DETACHED_PROCESS o hook espera a
        # indexação inteira. BREAKAWAY_FROM_JOB pode ser negado pelo job pai;
        # nesse caso tenta sem ele.
        detached = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        try:
            subprocess.Popen(_index_argv(root, event),
                             creationflags=detached | 0x01000000, **kwargs)
        except OSError:
            subprocess.Popen(_index_argv(root, event), creationflags=detached, **kwargs)
    else:
        subprocess.Popen(_index_argv(root, event), start_new_session=True, **kwargs)
    log.close()


def _refresh_status(root: Path) -> None:
    try:
        from ragx.config import load_config
        from ragx.indexing import status_file

        status_file.write_status(load_config(root))
    except Exception:
        pass
