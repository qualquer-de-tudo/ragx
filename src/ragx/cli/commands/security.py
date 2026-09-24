"""`ragx security scan` e `ragx security rules`.

É o comando que o dev roda antes de confiar no sistema — e o que o pre-commit
usa para barrar segredo antes do commit.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import load_config
from ragx.core.models import Severity, Verdict
from ragx.procs import run_quiet

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("scan")
def scan(
    path: Annotated[Path, typer.Argument(help="Raiz a varrer.")] = Path("."),
    as_json: Annotated[bool, typer.Option("--json", help="Saída estruturada.")] = False,
    fail_on: Annotated[
        str, typer.Option("--fail-on", help="critical|high|medium|low")
    ] = "high",
    staged: Annotated[
        bool, typer.Option("--staged", help="Só arquivos no stage do Git (pre-commit).")
    ] = False,
    rule: Annotated[str | None, typer.Option("--rule", help="Testa uma regra isolada.")] = None,
) -> None:
    """Varre em busca de segredos sem indexar nada."""
    from ragx.security.gate import SecurityGate
    from ragx.security.scanner import load_ruleset
    from ragx.walk import iter_files

    cfg = load_config(path)
    root = cfg.root if cfg.has_config_file else Path(path).resolve()
    gate = SecurityGate(
        root,
        policy=cfg.security.policy,
        scan_content=cfg.security.scan_content,
        min_entropy=cfg.security.min_entropy,
        extra_exclude=cfg.index.exclude,
    )

    targets = _staged_files(root) if staged else None
    blocked: list[dict] = []
    redacted: list[dict] = []
    skipped: list[dict] = []
    worst = Severity.LOW
    seen = 0

    for cand in iter_files(root, gate, max_bytes=cfg.index.max_file_bytes, only=targets):
        seen += 1
        d = cand.decision
        if d.verdict is Verdict.SKIP:
            skipped.append({"path": cand.rel_path, "rule": d.rule_id})
        elif d.verdict is Verdict.BLOCK:
            f = d.findings[0] if d.findings else None
            if f and f.severity.rank > worst.rank:
                worst = f.severity
            blocked.append(
                {
                    "path": cand.rel_path,
                    "rule": d.rule_id,
                    "severity": f.severity.value if f else "critical",
                    "line": f.line if f else 0,
                    "preview": f.preview if f else "",
                }
            )
        elif d.verdict is Verdict.ALLOW_REDACTED:
            for f in d.findings:
                if f.severity.rank > worst.rank:
                    worst = f.severity
            redacted.append({"path": cand.rel_path, "findings": len(d.findings)})

    if rule:
        blocked = [b for b in blocked if rule in (b["rule"] or "")]
        redacted = []

    rs = load_ruleset(frozenset(cfg.security.disabled_rules))
    payload = {
        "root": str(root),
        "scanned": seen,
        "blocked": blocked,
        "redacted": redacted,
        "skipped": len(skipped),
        "ruleset": {"version": "builtin@1", "rules": rs.count, "disabled": sorted(rs.disabled)},
        "policy": cfg.security.policy,
    }

    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False))
    else:
        _render(payload, skipped)

    threshold = Severity(fail_on)
    failing = [b for b in blocked if Severity(b["severity"]).rank >= threshold.rank]
    raise typer.Exit(1 if failing else 0)


def _render(p: dict, skipped: list[dict]) -> None:
    console.print(f"\n[bold]Security scan[/] — {p['root']}\n")
    if p["blocked"]:
        console.print(f"  [bold red]BLOCKED ({len(p['blocked'])})[/]")
        for b in p["blocked"]:
            loc = f" (L{b['line']})" if b["line"] else ""
            console.print(f"    {b['path']:<34} [red]{b['rule']}{loc}[/]")
        console.print()
    if p["redacted"]:
        console.print(f"  [bold yellow]REDACTED ({len(p['redacted'])})[/]")
        for r in p["redacted"]:
            console.print(f"    {r['path']:<34} [yellow]{r['findings']} achado(s)[/]")
        console.print()
    if skipped:
        console.print(f"  [dim]SKIPPED ({len(skipped)})   por ignore/binário/tamanho[/]\n")
    rs = p["ruleset"]
    dis = f", {len(rs['disabled'])} desabilitadas" if rs["disabled"] else ", 0 desabilitadas"
    console.print(
        f"Ruleset: {rs['version']} ({rs['rules']} regras{dis})   Política: {p['policy']}"
    )
    if not p["blocked"]:
        console.print("[green]Nenhum achado bloqueante.[/]")


@app.command("rules")
def rules(
    show_disabled: Annotated[bool, typer.Option("--show-disabled")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lista as regras ativas e as desabilitadas."""
    from ragx.security.scanner import load_ruleset, rules_summary

    cfg = load_config()
    rs = load_ruleset(frozenset(cfg.security.disabled_rules))
    summary = rules_summary(rs)
    if as_json:
        console.print_json(json.dumps(summary, ensure_ascii=False))
        return
    console.print(f"\n[bold]Ruleset builtin@1[/] — {summary['count']} regras ativas\n")
    console.print("[bold]Nome de arquivo[/]")
    for r in summary["filename_rules"]:
        console.print(f"  {r}")
    console.print("\n[bold]Conteúdo[/]")
    for r in summary["content_rules"]:
        console.print(f"  {r}")
    if summary["disabled"]:
        console.print(f"\n[yellow]Desabilitadas ({len(summary['disabled'])}):[/]")
        for r in summary["disabled"]:
            console.print(f"  [yellow]{r}[/]")
    elif show_disabled:
        console.print("\n[green]Nenhuma regra desabilitada.[/]")


def _staged_files(root: Path) -> set[str] | None:
    try:
        out = run_quiet(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}
