"""Formatação do ContextPack.

O que sai daqui vai direto para um prompt, então a fonte precisa estar visível
em cada fragmento — sem isso o agente não consegue citar nem abrir o arquivo.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape

from ragx.context import format as fmt_mod
from ragx.context.engine import ContextPack
from ragx.security.redactor import safe_echo


def render(pack: ContextPack, fmt: str = "markdown", title: bool = True) -> str:
    """`title=False` omite `# Contexto — <consulta>`: o MCP o desliga, porque o
    agente já sabe a consulta (que pode ter 2.000 caracteres)."""
    if fmt == "json":
        return _json(pack)
    if fmt == "xml":
        return _xml(pack)
    return _markdown(pack, title)


def _label(f) -> str:  # type: ignore[no-untyped-def]
    return fmt_mod.label(f.document_path, f.start_line, f.end_line, f.heading_path or f.symbol)


def _markdown(pack: ContextPack, title: bool = True) -> str:
    parts = [
        (fmt_mod.header(i, f.document_path, f.start_line, f.end_line,
                        f.heading_path or f.symbol, f.compressed), f.content)
        for i, f in enumerate(pack.fragments, start=1)
    ]
    return fmt_mod.markdown(
        parts, len(pack.sources), pack.estimated_tokens, pack.budget, len(pack.dropped),
        title=safe_echo(pack.query) if title else None,
    )


def _xml(pack: ContextPack) -> str:
    out = [f'<context query="{escape(safe_echo(pack.query), {chr(34): "&quot;"})}">']
    for f in pack.fragments:
        out.append(
            f'  <fragment source="{escape(f.document_path)}" '
            f'lines="{f.start_line}-{f.end_line}" '
            f'compressed="{str(f.compressed).lower()}">'
        )
        out.append(f"    {escape(f.content)}")
        out.append("  </fragment>")
    out.append(
        f'  <meta tokens="{pack.estimated_tokens}" budget="{pack.budget}" '
        f'sources="{len(pack.sources)}" />'
    )
    out.append("</context>")
    return "\n".join(out)


def _json(pack: ContextPack) -> str:
    return json.dumps(
        {
            "query": safe_echo(pack.query),
            "intent": pack.intent,
            "estimated_tokens": pack.estimated_tokens,
            "budget": pack.budget,
            "sources": list(pack.sources),
            "cached": pack.cached,
            "fragments": [
                {
                    "project": f.project,
                    "chunk_id": f.chunk_id,
                    "document_path": f.document_path,
                    "lines": [f.start_line, f.end_line],
                    "symbol": f.symbol,
                    "heading_path": f.heading_path,
                    "score": round(f.score, 6),
                    "tokens": f.tokens,
                    "compressed": f.compressed,
                    "strategy": f.strategy,
                    "reason": f.reason,
                    "content": f.content,
                }
                for f in pack.fragments
            ],
            "dropped": [{"id": a, "why": b} for a, b in pack.dropped],
            "stats": pack.stats,
        },
        ensure_ascii=False,
        indent=2,
    )


def explain(pack: ContextPack) -> str:
    """Justifica cada fragmento incluído e cada descartado."""
    lines = [
        f"Intenção detectada: {pack.intent}",
        f"Orçamento: {pack.estimated_tokens} / {pack.budget} tokens",
        "",
        "INCLUÍDOS:",
    ]
    for i, f in enumerate(pack.fragments, start=1):
        why = f"via {f.reason}"
        if f.compressed:
            why += f", comprimido por '{f.strategy}'"
        lines.append(f"  [{i}] {_label(f)}")
        lines.append(f"       score {f.score:.4f} · {f.tokens} tokens · {why}")

    if pack.dropped:
        motivos: dict[str, int] = {}
        for _cid, why in pack.dropped:
            chave = why.split(":")[0]
            motivos[chave] = motivos.get(chave, 0) + 1
        lines.append("")
        lines.append(f"DESCARTADOS ({len(pack.dropped)}):")
        for motivo, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {n:>4}  {motivo}")
        exemplos = [d for d in pack.dropped if not d[1].startswith("mmr")][:5]
        if exemplos:
            lines.append("")
            lines.append("  exemplos:")
            for cid, why in exemplos:
                lines.append(f"    {cid[:14]}  {why}")

    if pack.stats:
        lines.append("")
        lines.append("ETAPAS:")
        for k in ("candidates", "raw_tokens", "kept", "compressed",
                  "graph_seeds", "graph_nodes", "graph_expanded", "graph_truncated",
                  "graph_only", "retrieve_ms", "dedup_ms",
                  "compress_ms", "total_ms"):
            if k in pack.stats:
                lines.append(f"  {k:<16} {pack.stats[k]}")
    return "\n".join(lines)
