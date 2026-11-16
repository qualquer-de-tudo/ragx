"""`ragx usage` — consumo real de tokens nas sessões do Claude Code, por projeto (RAGX-0205)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()

#: (rótulo, métrica, é caractere de resultado: mostra em ≈ tokens)
_LINHAS: tuple[tuple[str, str, bool], ...] = (
    ("turnos (respostas do modelo)", "turns", False),
    ("tokens no total", "total_tokens", False),
    ("  entrada", "input_tokens", False),
    ("  cache lido", "cache_read_tokens", False),
    ("  cache gravado", "cache_creation_tokens", False),
    ("  saída", "output_tokens", False),
    ("buscas", "search_calls", False),
    ("leituras", "read_calls", False),
    ("chamadas ao RAGX", "ragx_calls", False),
    ("resultado de busca (≈ tokens)", "search_result_chars", True),
    ("resultado de leitura (≈ tokens)", "read_result_chars", True),
)


def _num(v: float | None, chars: bool, por_token: int) -> str:
    if v is None:
        return "—"
    n = v / por_token if chars else v
    return f"{n:,.0f}".replace(",", ".")


def _projeto_unico(alvo: str) -> list[dict[str, Any]]:
    """O `--project`: o do registro quando a pasta está lá (com id e nome), senão só a pasta."""
    from ragx.usage import _norm, projetos_registrados

    pasta = Path(alvo).expanduser().resolve()
    for p in projetos_registrados():
        if _norm(p["path"]) == _norm(str(pasta)):
            return [p]
    return [{"id": None, "name": pasta.name, "path": str(pasta)}]


def usage(
    days: Annotated[int, typer.Option("--days", min=1, max=365, help="Janela, em dias.")] = 14,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Só este projeto (pasta). Padrão: todos os registrados no hub."),
    ] = None,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Relê todos os transcripts.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Consumo real de tokens e adoção do RAGX, lidos das sessões do Claude Code.

    Lê os transcripts de todos os perfis do Claude Code (os de `ragx claude status`) e soma, por
    sessão, turnos, tokens (entrada, cache lido, cache gravado, saída), buscas, leituras e chamadas
    ao RAGX. Agrupa por projeto pela pasta da sessão (raiz e worktrees) e põe lado a lado as
    medianas das sessões com e sem RAGX. É observação, não experimento: são tarefas diferentes.
    Só números saem daqui; nunca texto de prompt, resposta, comando ou caminho de arquivo.
    """
    from ragx import usage as u

    since = datetime.now(UTC) - timedelta(days=days)
    perfis = u.perfis_claude()
    projetos = _projeto_unico(project) if project else u.projetos_registrados()
    sessoes = u.coletar(since, perfis, cache=None if no_cache else u.cache_padrao())
    dados = u.relatorio(sessoes, projetos, days, since, perfis)

    if as_json:
        console.print_json(json.dumps(dados, ensure_ascii=False))
        return

    console.print(f"\n[bold]Consumo real nas sessões do Claude Code[/] — últimos {days} dias")
    console.print(f"[dim]{escape(u.NOTA)}[/]\n")
    if not perfis:
        console.print("  Nenhum perfil do Claude Code nesta máquina.\n")
        return
    if not projetos:
        console.print("  Nenhum projeto registrado no hub. Use [bold]ragx usage --project PASTA[/].\n")
        return
    if not dados["projects"]:
        console.print(
            f"  {dados['sessions_scanned']} sessão(ões) na janela, nenhuma num projeto do RAGX.\n"
        )
        return

    por_token = int(dados["chars_per_token"])
    for p in dados["projects"]:
        com, sem = p["with_ragx"], p["without_ragx"]
        tabela = Table(
            title=f"{escape(str(p['name']))} · {p['sessions']} sessões "
            f"({com['sessions']} com RAGX, {sem['sessions']} sem)",
            title_justify="left",
        )
        tabela.add_column("mediana por sessão")
        tabela.add_column("com RAGX", justify="right")
        tabela.add_column("sem RAGX", justify="right")
        for rotulo, metrica, chars in _LINHAS:
            tabela.add_row(
                rotulo,
                _num(com["median"][metrica], chars, por_token),
                _num(sem["median"][metrica], chars, por_token),
            )
        console.print(tabela)
        a = p["adoption"]
        linha = f"  Adoção: {a['with_ragx']} de {a['sessions']} sessões chamaram o RAGX"
        if a["reminded"]:
            linha += f"; lembrete em {a['reminded']}, {a['ragx_after_reminder']} chamaram o RAGX depois dele"
        console.print(linha + ".\n")

    if dados["sessions_outside_projects"]:
        console.print(
            f"  [dim]{dados['sessions_outside_projects']} sessão(ões) fora dos projetos do RAGX não entram.[/]\n"
        )
