"""Parsers: extraem ESTRUTURA, não chunks.

A separação parser/chunker permite mudar a estratégia de fatiamento sem tocar
em parser nenhum. Ver ADR-0005.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from ragx.core.models import DocKind, ParseResult
from ragx.indexing.parsers.markdown import MarkdownParser
from ragx.indexing.parsers.python_ast import PythonParser
from ragx.indexing.parsers.structured import StructuredParser
from ragx.indexing.parsers.text import TextParser

# Lista FECHADA no MVP. Adicionar linguagem é ticket próprio, com fixture própria.
EXT_LANG: dict[str, tuple[str, DocKind]] = {
    ".md": ("markdown", DocKind.DOC),
    ".markdown": ("markdown", DocKind.DOC),
    ".txt": ("text", DocKind.DOC),
    ".rst": ("text", DocKind.DOC),
    ".py": ("python", DocKind.CODE),
    ".pyi": ("python", DocKind.CODE),
    ".php": ("php", DocKind.CODE),
    ".js": ("javascript", DocKind.CODE),
    ".jsx": ("javascript", DocKind.CODE),
    ".ts": ("typescript", DocKind.CODE),
    ".tsx": ("typescript", DocKind.CODE),
    ".json": ("json", DocKind.CONFIG),
    ".yaml": ("yaml", DocKind.CONFIG),
    ".yml": ("yaml", DocKind.CONFIG),
    ".xml": ("xml", DocKind.DATA),
    ".sql": ("sql", DocKind.CODE),
    ".toml": ("toml", DocKind.CONFIG),
}

_MARKDOWN = MarkdownParser()
_PYTHON = PythonParser()
_STRUCTURED = StructuredParser()
_TEXT = TextParser()

_BY_LANG = {
    "markdown": _MARKDOWN,
    "python": _PYTHON,
    "json": _STRUCTURED,
    "yaml": _STRUCTURED,
    "toml": _STRUCTURED,
    "xml": _STRUCTURED,
    "sql": _STRUCTURED,
}


def detect(rel_path: str) -> tuple[str, DocKind] | None:
    return EXT_LANG.get(PurePosixPath(rel_path).suffix.lower())


def parse(rel_path: str, content: str, include_unknown: bool = False) -> ParseResult | None:
    """None = extensão fora da lista fechada e include_unknown desligado."""
    hit = detect(rel_path)
    if hit is None:
        if not include_unknown:
            return None
        lang, kind = "text", DocKind.DOC
    else:
        lang, kind = hit

    parser = _BY_LANG.get(lang, _TEXT)
    try:
        result = parser.parse(rel_path, content, lang, kind)
    except Exception:
        # Falha de parsing NUNCA derruba a indexação: degrada para fallback.
        result = _TEXT.parse(rel_path, content, lang, kind)
        result = ParseResult(result.nodes, lang, kind, degraded=True, title=result.title)
    return result


__all__ = ["EXT_LANG", "detect", "parse"]
