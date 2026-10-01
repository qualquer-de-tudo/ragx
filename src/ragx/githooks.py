"""Hooks de git que mantêm o índice na branch em que você está.

Cada hook ganha um bloco marcado por raiz de projeto, então convive com hooks
de outras ferramentas e com mais de um projeto RAGX no mesmo repositório. O
bloco chama `ragx hook-run`, que dispara a indexação destacada e devolve o
terminal na hora. Opt-out por RAGX_SKIP_HOOK=1.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from ragx import gitinfo, hooklight
from ragx.core.errors import UsageError

EVENTS = hooklight.EVENTS
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


#: Em `post-checkout`, o 3º argumento do git é 1 só na troca de branch (0 é checkout de arquivo).
#: A guarda fica no SHELL do hook: `git checkout -- arquivo` não sobe Python nenhum (RAGX-0143).
_GUARDA_CHECKOUT = '[ "$3" = "1" ]'


def _condicao(event: str) -> str:
    base = '[ "$RAGX_SKIP_HOOK" != "1" ]'
    return f"{base} && {_GUARDA_CHECKOUT}" if event == "post-checkout" else base


def _block(root: Path, event: str, prefix: str) -> str:
    start, end = _markers(root)
    return (
        f"{start}\n"
        f"if {_condicao(event)}; then\n"
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
    gitinfo.hooks_dir_cache_clear()  # core.hooksPath pode ter mudado desde a última consulta
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
    gitinfo.hooks_dir_cache_clear()
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
        # blocos de formato antigo (sem a guarda de shell): `ragx hooks install` os reescreve
        "outdated": _desatualizados(d, root, events),
    }


def _desatualizados(d: Path | None, root: Path, events: dict[str, bool]) -> list[str]:
    if d is None:
        return []
    start, end = _markers(root)
    out: list[str] = []
    for event in EVENTS:
        path = d / event
        if not events.get(event) or not path.exists():
            continue
        linhas = path.read_text(encoding="utf-8").splitlines()
        try:
            bloco = linhas[linhas.index(start) : linhas.index(end)]
        except ValueError:
            continue
        if event == "post-checkout" and not any(_GUARDA_CHECKOUT in linha for linha in bloco):
            out.append(event)
    return out


def installed(root: Path) -> bool | None:
    estado = state(root)
    if estado["hooks_dir"] is None:
        return None
    return bool(estado["installed"])


# Reexportados de `ragx.hooklight`, que roda sem importar a CLI inteira (RAGX-0143).
should_run = hooklight.should_run
_index_argv = hooklight.index_argv
spawn_index = hooklight.spawn_index


def _refresh_status(root: Path) -> None:
    try:
        from ragx.config import load_config
        from ragx.indexing import status_file

        status_file.write_status(load_config(root))
    except Exception:
        pass
