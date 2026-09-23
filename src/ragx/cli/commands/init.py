"""`ragx init` — cria .ragx/, ragx.toml, .ragignore e ajusta o .gitignore."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import CONFIG_NAME, load_config

console = Console()

_RAGIGNORE = """# .ragignore — o que o RAGX não deve indexar.
# Segredos já são bloqueados pelo scanner, independente deste arquivo.

dist/
build/
coverage/
*.csv
*.parquet
**/*.generated.*
"""

_GITIGNORE_BLOCK = """
# RAGX — derivado e descartável, nunca versionar
.ragx/
*.rag
"""


def _project_id(root: Path) -> str:
    """Derivado do remote quando existir (por HASH — a URL pode conter token)."""
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root, capture_output=True, text=True, check=True, timeout=5,
        )
        seed = out.stdout.strip()
    except Exception:
        seed = ""
    if not seed:
        seed = f"local:{root.name}:{root.resolve().as_posix()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def init(
    path: Annotated[Path, typer.Argument()] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Sobrescreve ragx.toml.")] = False,
    name: Annotated[str | None, typer.Option("--name")] = None,
) -> None:
    """Prepara o projeto para o RAGX."""
    from ragx.core.ids import CHUNKER_VERSION, SCHEMA_VERSION
    from ragx.storage.db import open_db, set_meta, utcnow

    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cfg_path = root / CONFIG_NAME
    created: list[str] = []

    if cfg_path.exists() and not force:
        console.print(f"[yellow]{CONFIG_NAME} já existe.[/] Use --force para sobrescrever.")
    else:
        pid = _project_id(root)
        cfg_path.write_text(
            f'[project]\nname = "{name or root.name}"\nid = "{pid}"\n'
            'kind = "other"\nvisibility = "workspace"\n\n'
            "[security]\npolicy = \"strict\"\n\n"
            "[index]\nmax_file_bytes = 1048576\n",
            encoding="utf-8",
        )
        created.append(CONFIG_NAME)

    ragignore = root / ".ragignore"
    if not ragignore.exists():
        ragignore.write_text(_RAGIGNORE, encoding="utf-8")
        created.append(".ragignore")

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".ragx/" not in existing:
        gitignore.write_text(existing + _GITIGNORE_BLOCK, encoding="utf-8")
        created.append(".gitignore (bloco RAGX)")

    cfg = load_config(root)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "logs").mkdir(exist_ok=True)
    (cfg.state_dir / "cache").mkdir(exist_ok=True)

    with open_db(cfg.db_path) as conn:
        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        set_meta(conn, "chunker_version", CHUNKER_VERSION)
        set_meta(conn, "project_id", cfg.project.id)
        set_meta(conn, "project_name", cfg.project.name)
        set_meta(conn, "project_kind", cfg.project.kind)
        set_meta(conn, "visibility", cfg.project.visibility)
        set_meta(conn, "created_at", utcnow())
        conn.commit()
        created.append(".ragx/knowledge.db")

    console.print(f"\n[bold green]RAGX inicializado[/] em {root}\n")
    for c in created:
        console.print(f"  [green]+[/] {c}")
    if not created:
        console.print("  [dim]nada a fazer — já estava inicializado[/]")
    console.print(f"\n  project_id: [cyan]{cfg.project.id}[/]")

    from ragx.core.errors import UsageError
    from ragx.federation import hub as hub_mod

    try:
        hub_mod.register(cfg, path=root)
        console.print(f"  [dim]registrado no hub ({cfg.hub_dir})[/]")
    except UsageError:
        # Projeto private, ou (raro) ragx.toml sumiu entre a escrita acima e
        # aqui: registro no hub é um extra, nao motivo pra falhar o init.
        pass

    console.print("\nPróximo passo: [bold]ragx security scan .[/]\n")
