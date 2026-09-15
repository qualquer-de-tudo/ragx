"""`ragx agent create|train|list|show|eval|promote-example|export`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.agents import evaluator, profile, trainer
from ragx.config import load_config

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command("create")
def create(
    name: Annotated[str, typer.Argument()],
    template: Annotated[str, typer.Option("--template")] = "backend",
    scope: Annotated[str | None, typer.Option("--scope")] = None,
) -> None:
    """Cria o esqueleto de um perfil de agente."""
    r = profile.create(load_config(), name, template, scope)
    console.print(f"\n[bold green]Perfil criado[/] — {r.path}  [dim]({r.template})[/]\n")
    for c in r.created:
        console.print(f"  [green]+[/] {c}")
    console.print(f"\nPróximo passo: [bold]ragx agent train {name}[/]\n")


@app.command("train")
def train(
    name: Annotated[str, typer.Argument()],
    tokens: Annotated[int, typer.Option("--tokens")] = 6000,
    with_examples: Annotated[bool, typer.Option("--with-examples")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compila conhecimento, regras e skills no perfil."""
    r = trainer.train(load_config(), name, tokens, with_examples)
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "name": r.name, "tokens": r.tokens, "rules": r.rules,
                    "generated_rules": r.generated_rules, "preserved": r.preserved,
                    "skills": r.skills, "proposed_examples": r.proposed_examples,
                    "dictionary_items": r.dictionary_items, "warnings": r.warnings,
                },
                ensure_ascii=False,
            )
        )
        return
    console.print(f"\n[bold green]Perfil treinado[/] — {r.name}\n")
    console.print(f"  instructions.md  {r.tokens:>6} tokens")
    console.print(f"  regras           {r.rules:>6}  [dim]({r.generated_rules} gerada(s))[/]")
    console.print(f"  skills           {r.skills:>6}")
    console.print(f"  dicionário       {r.dictionary_items:>6} itens")
    if r.proposed_examples:
        console.print(
            f"  [yellow]{r.proposed_examples} exemplo(s) propostos[/] "
            "[dim]— promova com `ragx agent promote-example`[/]"
        )
    if r.preserved:
        console.print(f"\n  [dim]preservadas: {', '.join(r.preserved)}[/]")
    for w in r.warnings:
        console.print(f"  [yellow]! {w}[/]")
    console.print()


@app.command("list")
def list_(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Perfis existentes."""
    names = profile.list_profiles(load_config())
    if as_json:
        console.print_json(json.dumps(names, ensure_ascii=False))
        return
    if not names:
        console.print("\n[dim]nenhum perfil — `ragx agent create <nome>`[/]\n")
        return
    console.print()
    for n in names:
        console.print(f"  {n}")
    console.print()


@app.command("show")
def show(
    name: Annotated[str, typer.Argument()],
    section: Annotated[str | None, typer.Option("--section")] = None,
) -> None:
    """Mostra o perfil."""
    cfg = load_config()
    manifest, paths = profile.load(cfg, name)
    if section in ("rules", "skills"):
        folder = paths.rules if section == "rules" else paths.skills
        for p in sorted(folder.glob("*.md")):
            console.print(f"  [cyan]{p.name}[/]")
        return
    console.print(f"\n[bold]{manifest.name}[/] v{manifest.version}\n")
    console.print(f"  {manifest.description}")
    console.print(f"\n  escopo      {', '.join(manifest.scope.include_paths)}")
    console.print(f"  chunks      {manifest.knowledge.chunks:,}")
    console.print(f"  entidades   {manifest.knowledge.entities:,}")
    console.print(f"  gerado em   {manifest.generated_at or '—'}\n")


@app.command("eval")
def eval_(
    name: Annotated[str, typer.Argument()],
    case: Annotated[str | None, typer.Option("--case")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Avalia a RECUPERAÇÃO do perfil (não a geração)."""
    r = evaluator.evaluate(load_config(), name, case)
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "name": r.name, "recall_at_3": round(r.recall_at_3, 4),
                    "passed": r.passed, "total": len(r.results),
                    "cases": [
                        {"id": c.id, "passed": c.passed, "rank": c.rank,
                         "failures": c.failures}
                        for c in r.results
                    ],
                },
                ensure_ascii=False,
            )
        )
        raise typer.Exit(0 if r.passed == len(r.results) else 1)

    console.print(f"\n[bold]Avaliação[/] — {r.name}\n")
    for c in r.results:
        marca = "[green]OK[/]" if c.passed else "[red]FALHOU[/]"
        console.print(f"  {c.id:<12} {marca}  [dim]rank={c.rank or '—'}[/]")
        for f in c.failures:
            console.print(f"    [yellow]{f}[/]")
    console.print(
        f"\n  {len(r.results)} caso(s) · {r.passed} aprovado(s) · "
        f"Recall@3 = {r.recall_at_3:.2f}"
    )
    console.print("  [dim]mede recuperação de contexto, não qualidade da resposta[/]\n")
    raise typer.Exit(0 if r.passed == len(r.results) else 1)


@app.command("promote-example")
def promote(
    name: Annotated[str, typer.Argument()],
    example_id: Annotated[str, typer.Argument()],
) -> None:
    """Promove um exemplo proposto. Exemplo ruim ensina padrão ruim."""
    dst = trainer.promote_example(load_config(), name, example_id)
    console.print(f"\n[green]✓[/] {dst}\n")


@app.command("export")
def export(
    name: Annotated[str, typer.Argument()],
    out: Annotated[Path, typer.Option("--out")] = Path("perfil.zip"),
) -> None:
    """Empacota o perfil para uso em outro projeto."""
    import zipfile

    cfg = load_config()
    _m, paths = profile.load(cfg, name)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths.root.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(paths.root).as_posix())
    console.print(f"\n[green]✓[/] {out}  [dim]{out.stat().st_size / 1024:.1f} KB[/]\n")
