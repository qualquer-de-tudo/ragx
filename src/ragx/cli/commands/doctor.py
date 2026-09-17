"""`ragx doctor` — diagnóstico com sugestão acionável por falha."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import CONFIG_NAME, load_config

console = Console()


class _Relatorio:
    """Junta as checagens uma vez e decide DEPOIS como apresentá-las.

    O `doctor` só sabia falar com gente. O plugin do VS Code precisa das
    mesmas checagens em JSON — e reimplementá-las do outro lado produziria
    dois diagnósticos que discordam sobre o mesmo ambiente.
    """

    def __init__(self, como_json: bool) -> None:
        self.como_json = como_json
        self.checks: list[dict[str, object]] = []

    def row(self, label: str, value: str, ok: bool, hint: list[str] | None = None) -> bool:
        self.checks.append(
            {"name": label, "ok": ok, "detail": value, "hints": list(hint or [])}
        )
        if self.como_json:
            return ok
        mark = "[green]ok[/]" if ok else "[bold red]FALHA[/]"
        console.print(f"  {label:<18}{value:<44}{mark}")
        # Sugestão de correção só cabe quando a checagem falhou — imprimir
        # "ragx reset" ao lado de um "ok" faz a pessoa achar que há algo errado.
        if not ok:
            for h in hint or []:
                console.print(f"                    [yellow]→ {h}[/]")
        return ok


def doctor(
    full: Annotated[bool, typer.Option("--full", help="Inclui integridade do banco.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Valida o ambiente e a configuração."""
    from ragx.core.ids import SCHEMA_VERSION
    from ragx.security.scanner import load_ruleset
    from ragx.storage.db import integrity_check, open_db, user_version

    cfg = load_config()
    rel = _Relatorio(as_json)
    _row = rel.row
    if not as_json:
        console.print("\n[bold]ragx doctor[/]\n")
    problems = 0

    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    problems += not _row("Python", py, sys.version_info >= (3, 11), ["requer Python >= 3.11"])

    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        problems += not _row("SQLite", f"{sqlite3.sqlite_version} (FTS5 ✓)", True)
    except sqlite3.OperationalError:
        problems += not _row(
            "SQLite", f"{sqlite3.sqlite_version} (sem FTS5)", False,
            ["instale um Python cujo SQLite tenha FTS5"],
        )

    problems += not _row(
        "Projeto", str(cfg.root), True,
        [] if cfg.has_config_file else [f"{CONFIG_NAME} ausente — rode: ragx init"],
    )
    problems += not _row(
        "Config", f"{CONFIG_NAME} {'encontrado' if cfg.has_config_file else 'ausente (defaults)'}",
        cfg.has_config_file, [] if cfg.has_config_file else ["ragx init"],
    )

    rs = load_ruleset(frozenset(cfg.security.disabled_rules))
    dis = len(rs.disabled)
    problems += not _row(
        "Ruleset", f"builtin@1 — {rs.count} regras, {dis} desabilitadas", dis == 0,
        [f"regras desabilitadas enfraquecem o gate: {sorted(rs.disabled)}"] if dis else [],
    )

    if cfg.db_path.exists():
        try:
            with open_db(cfg.db_path) as conn:
                v = user_version(conn)
                problems += not _row(
                    "Schema", f"v{v} (suportado: v{SCHEMA_VERSION})", v <= SCHEMA_VERSION,
                    ["banco mais novo que esta instalação — atualize o RAGX"],
                )
                if full:
                    res = integrity_check(conn)
                    problems += not _row("Integridade", res, res == "ok", ["ragx reset"])
                    orfaos = _orphans(conn)
                    total = sum(orfaos.values())
                    problems += not _row(
                        "Consistência",
                        "sem órfãos" if total == 0 else f"{total} órfão(s)",
                        total == 0,
                        [f"{k}: {v}" for k, v in orfaos.items() if v] + ["ragx vacuum"],
                    )
        except Exception as exc:
            problems += not _row("Schema", str(exc)[:42], False, ["ragx reset"])
    else:
        problems += not _row("Banco", "ausente", False, ["ragx init"])

    writable = True
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        probe = cfg.state_dir / ".write_probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
    except OSError:
        writable = False
    problems += not _row("Escrita .ragx/", "permitida" if writable else "negada", writable,
                         [] if writable else ["verifique permissões do diretório"])

    ok = _embedder_status(cfg, _row)
    if not ok:
        problems += 1

    if as_json:
        # Sai com 0 mesmo havendo problema: o diagnóstico está no payload, e
        # quem pede JSON quer LÊ-LO. Código de saída diferente de zero faz o
        # chamador descartar a saída inteira e ficar sem diagnóstico nenhum —
        # foi o que aconteceu com o plugin do VS Code, que mostrava "erro ao
        # falar com o RAGX" no lugar das checagens.
        console.print_json(
            json.dumps(
                {"ok": problems == 0, "problems": problems, "checks": rel.checks},
                ensure_ascii=False,
            )
        )
        return

    console.print()
    if problems:
        console.print(f"[bold yellow]{problems} problema(s).[/] Busca semântica pode estar "
                      "indisponível; keyword continua funcionando.\n")
        raise typer.Exit(3 if problems > 1 else 1)
    console.print("[bold green]Tudo certo.[/]\n")


def _embedder_status(cfg, _row) -> bool:  # type: ignore[no-untyped-def]
    provider = cfg.embedding.provider
    try:
        from ragx.embeddings import build_embedder

        ident = build_embedder(cfg).id
    except Exception:
        ident = f"{provider}:{cfg.embedding.model}"
    label = f"{ident} ({cfg.embedding.dim}d)"
    if provider == "hashing":
        return _row("Embedder", label + "  — só testes", True)
    if provider == "ollama":
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"{cfg.embedding.base_url}/api/tags", timeout=2) as r:
                body = r.read().decode("utf-8", "replace")
            if cfg.embedding.model.split(":")[0] in body:
                return _row("Embedder", label, True)
            return _row("Embedder", label, False, [
                f"modelo ausente: ollama pull {cfg.embedding.model}"])
        except (urllib.error.URLError, OSError, TimeoutError):
            return _row("Embedder", label, False, [
                f"conexão recusada em {cfg.embedding.base_url}",
                "inicie o daemon: ollama serve",
                "ou use: ragx config set embedding.provider fastembed",
            ])
    return _row("Embedder", label, True)


def _orphans(conn) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Inconsistência entre tabelas que o integrity_check do SQLite não pega."""
    checks = {
        "embeddings sem chunk":
            "SELECT COUNT(*) FROM embeddings WHERE chunk_id NOT IN (SELECT id FROM chunks)",
        "chunks sem documento":
            "SELECT COUNT(*) FROM chunks WHERE document_id NOT IN (SELECT id FROM documents)",
        "relações sem entidade":
            "SELECT COUNT(*) FROM relations WHERE src_id NOT IN (SELECT id FROM entities) "
            "OR dst_id NOT IN (SELECT id FROM entities)",
        "FTS dessincronizado":
            "SELECT ABS((SELECT COUNT(*) FROM chunks_fts) - (SELECT COUNT(*) FROM chunks))",
    }
    out: dict[str, int] = {}
    for label, sql in checks.items():
        try:
            out[label] = int(conn.execute(sql).fetchone()[0])
        except Exception:
            out[label] = 0
    return out
