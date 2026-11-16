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
    cached: Annotated[
        bool,
        typer.Option(
            "--cached",
            help="Reaproveita o que o índice já examinou e lê só o que mudou desde então (o painel usa).",
        ),
    ] = False,
) -> None:
    """Varre em busca de segredos sem indexar nada."""
    from ragx.security.gate import SecurityGate
    from ragx.security.scanner import load_ruleset
    from ragx.walk import iter_files, iter_paths

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
    reused = 0
    mode = "full"

    estado = _estado_do_indice(cfg) if cached and not staged else None
    if estado is not None:
        mode = "cache"
    elif cached and not staged:
        mode = "full (sem índice válido)"

    if staged and targets is not None:
        # Só os arquivos do stage: `iter_paths` os examina um a um (mesmo Gate, mesmas recusas da varredura) em vez
        # de listar a árvore inteira para depois filtrar; num projeto de 18 mil arquivos isso eram ~11 s.
        # `targets is None` (o git falhou) NÃO entra aqui: sem lista confiável, varre tudo, como sempre.
        origem = iter_paths(root, gate, sorted(targets), max_bytes=cfg.index.max_file_bytes)
    else:
        origem = iter_files(
            root, gate, max_bytes=cfg.index.max_file_bytes,
            fingerprints=estado.fingerprints if estado else None,
            verdicts=estado.verdicts if estado else None,
        )

    for cand in origem:
        seen += 1
        if estado is not None and (cand.unchanged or cand.cached_verdict):
            reused += 1
            achado = estado.achado(cand.rel_path, cand.decision)
            if achado is None:
                # sem os eventos do índice para este arquivo: não dá para reportar sem ler, então lê
                from ragx.walk import Candidate, read_candidate

                lido = read_candidate(
                    Candidate(str(root / cand.rel_path), cand.rel_path, cand.rel_path, cand.size_bytes, cand.mtime_ns),
                    gate,
                )
                if lido is None:
                    continue
                reused -= 1
                cand = lido
            else:
                tipo, entrada, severidade = achado
                if tipo == "blocked":
                    blocked.append(entrada)
                elif tipo == "redacted":
                    redacted.append(entrada)
                elif cand.decision.verdict is Verdict.SKIP and cand.decision.rule_id in ("binary", "undecodable"):
                    # os mesmos que a varredura completa conta como ignorados; "unsupported" (sem parser) é decisão
                    # do índice, não do Gate: lá o arquivo é só um arquivo limpo
                    skipped.append({"path": cand.rel_path, "rule": cand.decision.rule_id})
                if severidade is not None and severidade.rank > worst.rank:
                    worst = severidade
                continue
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
        # `cache`: parte veio do índice (RAGX-0206); `reused` é quantos arquivos não foram reabertos.
        "mode": mode,
        "reused": reused,
    }

    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False))
    else:
        _render(payload, skipped)

    threshold = Severity(fail_on)
    failing = [b for b in blocked if Severity(b["severity"]).rank >= threshold.rank]
    raise typer.Exit(1 if failing else 0)


class _EstadoDoIndice:
    """O que o índice já examinou, para o scan `--cached` não reabrir o que não mudou (RAGX-0206).

    Mesma confiança do próprio índice: `size`+`mtime_ns` iguais, e só com o contexto do veredito (regras do Gate,
    política, limites) idêntico ao gravado. Arquivo bloqueado ou censurado volta pelos eventos de segurança que o
    índice gravou (regra, severidade, linha e trecho JÁ censurado: nunca o segredo).

    Limite conhecido: o índice só grava os eventos de um arquivo DEPOIS de saber se há parser para ele; um arquivo
    sem parser (`unsupported`) com achado fraco (censurado, não bloqueado) não tem evento guardado, então o modo com
    cache o trata como limpo. Ele não entra no índice, e a varredura completa (o padrão da CLI) continua o mostrando.
    """

    def __init__(
        self,
        fingerprints: dict[str, tuple[int, int]],
        verdicts: dict[str, tuple[int, int, str, str | None]],
        eventos: dict[str, list[dict]],
    ) -> None:
        self.fingerprints = fingerprints
        self.verdicts = verdicts
        self.eventos = eventos

    def achado(self, rel: str, decisao) -> tuple[str, dict, Severity | None] | None:  # type: ignore[no-untyped-def]
        """`(tipo, entrada do JSON, severidade)`; `("limpo", {}, None)` se não há achado; `None` = ler de novo."""
        eventos = self.eventos.get(rel, [])
        if decisao.verdict is Verdict.BLOCK:
            regra = decisao.rule_id
            if not eventos:
                return None
            f = next((e for e in eventos if e["rule"] == regra), eventos[0])
            return (
                "blocked",
                {"path": rel, "rule": regra, "severity": f["severity"], "line": f["line"] or 0, "preview": f["preview"] or ""},
                Severity(f["severity"]),
            )
        if decisao.verdict is Verdict.SKIP:
            return ("limpo", {}, None)
        redigidos = [e for e in eventos if e["action"] == "redact"]
        if not redigidos:
            return ("limpo", {}, None)
        pior = max((Severity(e["severity"]) for e in redigidos), key=lambda s: s.rank)
        return ("redacted", {"path": rel, "findings": len(redigidos)}, pior)


def _estado_do_indice(cfg) -> _EstadoDoIndice | None:  # type: ignore[no-untyped-def]
    """`None` quando não há índice, ele é de outra versão ou o contexto do veredito mudou: aí vale a varredura toda."""
    if not cfg.db_path.exists():
        return None
    from ragx.core.ids import CHUNKER_VERSION
    from ragx.indexing import verdicts as vmod
    from ragx.storage.db import get_meta, open_db
    from ragx.storage.repositories import DocumentRepo, VerdictRepo

    try:
        with open_db(cfg.db_path, read_only=True) as conn:
            if get_meta(conn, vmod.META_KEY) != vmod.verdict_context(cfg):
                return None
            docs = DocumentRepo(conn).fingerprints()
            verdicts = VerdictRepo(conn).load(None)
            eventos: dict[str, list[dict]] = {}
            for r in conn.execute(
                "SELECT path, rule_id, severity, action, line, preview FROM security_events ORDER BY id"
            ):
                eventos.setdefault(r["path"], []).append(
                    {"rule": r["rule_id"], "severity": r["severity"], "action": r["action"],
                     "line": r["line"], "preview": r["preview"]}
                )
    except Exception:
        return None
    fingerprints = {p: (s, m) for p, (_h, s, m, cv) in docs.items() if cv == CHUNKER_VERSION}
    return _EstadoDoIndice(fingerprints, verdicts, eventos)


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
