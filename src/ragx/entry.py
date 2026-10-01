"""Ponto de entrada de `ragx` e `rag` (só stdlib), RAGX-0143.

`ragx.cli.main` importa typer, rich, pydantic e 25 módulos de comando antes de olhar o primeiro
argumento: cerca de 480 ms. Os três comandos que os hooks rodam a cada sessão, edição e commit não
precisam de nada disso, então este módulo olha `sys.argv` primeiro:

- `ragx claude hint`            -> `ragx.hooklight.run_hint`
- `ragx claude nudge`           -> `ragx.hooklight.run_nudge`
- `ragx touch --stdin-json`     -> `ragx.hooklight.run_touch`
- `ragx hook-run EVENT --root`  -> `ragx.hooklight.run_hook`

Todo o resto (e qualquer variação desses três que a entrada leve não reconheça) vai para a CLI
completa, com o mesmo comportamento e as mesmas mensagens de erro de antes.
"""

from __future__ import annotations

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv == ["claude", "hint"]:
        from ragx.hooklight import run_hint

        raise SystemExit(run_hint())
    if argv == ["claude", "nudge"]:
        from ragx.hooklight import run_nudge

        raise SystemExit(run_nudge())
    if argv == ["touch", "--stdin-json"]:
        from ragx.hooklight import run_touch

        raise SystemExit(run_touch())
    if argv and argv[0] == "hook-run":
        from ragx.hooklight import parse_hook_run, run_hook

        if parse_hook_run(argv[1:]) is not None:
            raise SystemExit(run_hook(argv[1:]))
    from ragx.cli.main import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
