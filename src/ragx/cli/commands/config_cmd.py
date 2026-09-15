"""`ragx config show|get|set`."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import CONFIG_NAME, load_config
from ragx.core.errors import UsageError

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("show")
def show(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Configuração efetiva, depois de toda a cascata."""
    cfg = load_config()
    data = cfg.model_dump()
    if as_json:
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))
        return
    console.print(f"\n[bold]Configuração efetiva[/]  raiz={cfg.root}")
    console.print(f"[dim]{CONFIG_NAME}: {'encontrado' if cfg.has_config_file else 'ausente'}[/]\n")
    for section, values in data.items():
        console.print(f"[bold cyan]\\[{section}][/]")
        for k, v in values.items():
            console.print(f"  {k} = {v!r}")
        console.print()


@app.command("get")
def get(key: Annotated[str, typer.Argument(help="secao.chave")]) -> None:
    cfg = load_config()
    if "." not in key:
        raise UsageError("use o formato secao.chave (ex.: security.policy)")
    section, field = key.split(".", 1)
    data = cfg.model_dump()
    if section not in data or field not in data[section]:
        raise UsageError(f"chave desconhecida: {key}")
    console.print(data[section][field])


@app.command("set")
def set_(
    key: Annotated[str, typer.Argument(help="secao.chave")],
    value: Annotated[str, typer.Argument()],
) -> None:
    """Grava no ragx.toml do projeto."""
    import tomllib

    cfg = load_config()
    if "." not in key:
        raise UsageError("use o formato secao.chave (ex.: security.policy)")
    section, field = key.split(".", 1)
    data = cfg.model_dump()
    if section not in data or field not in data[section]:
        raise UsageError(f"chave desconhecida: {key}")

    path = cfg.root / CONFIG_NAME
    raw = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw.setdefault(section, {})[field] = _parse(value)
    path.write_text(_dump(raw), encoding="utf-8")
    console.print(f"[green]{key}[/] = {_parse(value)!r}")


def _parse(v: str) -> object:
    low = v.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _dump(data: dict) -> str:
    out = []
    for section, values in data.items():
        out.append(f"[{section}]")
        for k, v in values.items():
            out.append(f"{k} = {json.dumps(v)}")
        out.append("")
    return "\n".join(out)
