"""JSON, YAML, TOML, XML e SQL — configuração e dados estruturados.

É onde mora boa parte do conhecimento de infraestrutura, e boa parte do risco
de segredo (que já foi barrado pelo gate antes de chegar aqui).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import PurePosixPath

from ragx.core.models import ChunkKind, DocKind, ParseNode, ParseResult

_SQL_STMT = re.compile(
    r"^\s*(CREATE\s+(?:TABLE|VIEW|INDEX|FUNCTION|PROCEDURE|TRIGGER)|ALTER|INSERT|"
    r"UPDATE|DELETE|SELECT|DROP|WITH)\b",
    re.IGNORECASE,
)
_SQL_NAME = re.compile(
    r"CREATE\s+(?:TABLE|VIEW|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([\w.]+)",
    re.IGNORECASE,
)
_YAML_TOP = re.compile(r"^([A-Za-z_][\w.\-]*)\s*:")
_XML_TOP = re.compile(r"^\s*<([A-Za-z_][\w.\-:]*)")


class StructuredParser:
    name = "structured"

    def parse(self, rel_path: str, content: str, lang: str, kind: DocKind) -> ParseResult:
        if lang == "sql":
            nodes = _sql(content)
        elif lang == "json":
            nodes = _json_like(content)
        elif lang == "toml":
            nodes = _toml(content)
        elif lang == "yaml":
            nodes = _yaml(content)
        else:
            nodes = _xml(content)
        if not nodes:
            nodes = [ParseNode(ChunkKind.BLOCK, 1, max(len(content.splitlines()), 1))]
        return ParseResult(tuple(nodes), lang, kind, title=PurePosixPath(rel_path).name)


def _line_of_key(lines: list[str], key: str, start: int = 0) -> int:
    needle = f'"{key}"'
    for i in range(start, len(lines)):
        if needle in lines[i] or lines[i].lstrip().startswith(key):
            return i + 1
    return start + 1


def _json_like(content: str) -> list[ParseNode]:
    lines = content.splitlines()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return [ParseNode(ChunkKind.BLOCK, 1, max(len(lines), 1))]
    keys = list(data)
    starts = []
    cursor = 0
    for k in keys:
        ln = _line_of_key(lines, k, cursor)
        starts.append(ln)
        cursor = ln
    out = []
    for i, k in enumerate(keys):
        end = (starts[i + 1] - 1) if i + 1 < len(starts) else len(lines)
        out.append(
            ParseNode(ChunkKind.BLOCK, starts[i], max(end, starts[i]), symbol=f"$.{k}")
        )
    return out


def _toml(content: str) -> list[ParseNode]:
    lines = content.splitlines()
    try:
        tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return []
    out: list[ParseNode] = []
    current: tuple[int, str] | None = None
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("["):
            if current:
                out.append(ParseNode(ChunkKind.BLOCK, current[0], i - 1, symbol=current[1]))
            current = (i, line.strip().strip("[]"))
    if current:
        out.append(ParseNode(ChunkKind.BLOCK, current[0], len(lines), symbol=current[1]))
    elif lines:
        out.append(ParseNode(ChunkKind.BLOCK, 1, len(lines)))
    return out


def _yaml(content: str) -> list[ParseNode]:
    """Sem dependência: corta por chave de topo e por separador de documento."""
    lines = content.splitlines()
    marks: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        if line.strip() == "---":
            marks.append((i, "---"))
            continue
        m = _YAML_TOP.match(line)
        if m:
            marks.append((i, m.group(1)))
    if not marks:
        return []
    out = []
    for idx, (ln, name) in enumerate(marks):
        end = marks[idx + 1][0] - 1 if idx + 1 < len(marks) else len(lines)
        out.append(ParseNode(ChunkKind.BLOCK, ln, max(end, ln), symbol=name))
    return out


def _xml(content: str) -> list[ParseNode]:
    lines = content.splitlines()
    out = []
    for i, line in enumerate(lines, start=1):
        m = _XML_TOP.match(line)
        if m and not line.lstrip().startswith(("<?", "<!")):
            out.append((i, m.group(1)))
    if not out:
        return []
    nodes = []
    for idx, (ln, name) in enumerate(out):
        end = out[idx + 1][0] - 1 if idx + 1 < len(out) else len(lines)
        nodes.append(ParseNode(ChunkKind.BLOCK, ln, max(end, ln), symbol=name))
    return nodes[:200]


def _sql(content: str) -> list[ParseNode]:
    lines = content.splitlines()
    starts: list[int] = [i for i, line in enumerate(lines, start=1) if _SQL_STMT.match(line)]
    if not starts:
        return []
    out = []
    for idx, ln in enumerate(starts):
        end = starts[idx + 1] - 1 if idx + 1 < len(starts) else len(lines)
        body = "\n".join(lines[ln - 1 : end])
        m = _SQL_NAME.search(body)
        out.append(
            ParseNode(
                ChunkKind.STATEMENT,
                ln,
                max(end, ln),
                symbol=m.group(1) if m else None,
                meta={"is_ddl": bool(m)},
            )
        )
    return out
