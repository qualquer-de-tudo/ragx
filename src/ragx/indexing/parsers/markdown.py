"""Parser de Markdown sem dependência externa.

Extrai a árvore de headings, que é a espinha dorsal do `heading_path`.
Blocos de código e tabelas são nós indivisíveis — o chunker nunca os parte.
"""

from __future__ import annotations

import re

from ragx.core.models import ChunkKind, DocKind, ParseNode, ParseResult

_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(\S*)")
_SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")


class MarkdownParser:
    name = "markdown"

    def parse(self, rel_path: str, content: str, lang: str, kind: DocKind) -> ParseResult:
        lines = content.splitlines()
        headings = _headings(lines)
        title = next((h[2] for h in headings if h[1] == 1), None)

        if not headings:
            end = len(lines) or 1
            return ParseResult(
                (ParseNode(ChunkKind.SECTION, 1, end, meta={"heading_path": ""}),),
                lang, kind, title=title,
            )

        nodes: list[ParseNode] = []
        if headings[0][0] > 1:
            nodes.append(
                ParseNode(ChunkKind.SECTION, 1, headings[0][0] - 1, meta={"heading_path": ""})
            )

        stack: list[tuple[int, str]] = []
        flat: list[ParseNode] = []
        for idx, (lineno, level, text) in enumerate(headings):
            end = headings[idx + 1][0] - 1 if idx + 1 < len(headings) else len(lines)
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = " > ".join([s[1] for s in stack] + [text])
            stack.append((level, text))
            flat.append(
                ParseNode(
                    ChunkKind.SECTION,
                    lineno,
                    max(end, lineno),
                    symbol=text,
                    meta={
                        "heading_path": path,
                        "level": level,
                        "protected": _protected_ranges(lines, lineno, max(end, lineno)),
                    },
                )
            )
        nodes.extend(flat)
        return ParseResult(tuple(nodes), lang, kind, title=title)


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """Ignora '#' dentro de bloco de código — a armadilha clássica."""
    out: list[tuple[int, int, str]] = []
    fence: str | None = None
    for i, line in enumerate(lines, start=1):
        f = _FENCE.match(line)
        if f:
            marker = f.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            continue
        if fence is not None:
            continue
        m = _ATX.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
            continue
        # setext: título sublinhado por === ou ---
        if i >= 2 and _SETEXT.match(line) and lines[i - 2].strip():
            level = 1 if line.strip().startswith("=") else 2
            out.append((i - 1, level, lines[i - 2].strip()))
    return out


def _protected_ranges(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    """Intervalos que o chunker não pode partir: fences e tabelas."""
    ranges: list[tuple[int, int]] = []
    fence_start: int | None = None
    fence_char: str | None = None
    table_start: int | None = None

    for i in range(start, min(end, len(lines)) + 1):
        line = lines[i - 1]
        f = _FENCE.match(line)
        if f:
            marker = f.group(1)
            if fence_start is None:
                fence_start, fence_char = i, marker[0]
            elif marker[0] == fence_char:
                ranges.append((fence_start, i))
                fence_start = fence_char = None
            continue
        if fence_start is not None:
            continue
        is_table_row = line.lstrip().startswith("|") and line.rstrip().endswith("|")
        if is_table_row and table_start is None:
            table_start = i
        elif not is_table_row and table_start is not None:
            ranges.append((table_start, i - 1))
            table_start = None

    if fence_start is not None:
        ranges.append((fence_start, end))
    if table_start is not None:
        ranges.append((table_start, end))
    return ranges
