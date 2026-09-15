"""Fallback: parágrafos. Rede de segurança para extensão desconhecida e para
falha de parsing."""

from __future__ import annotations

from ragx.core.models import ChunkKind, DocKind, ParseNode, ParseResult


class TextParser:
    name = "text"

    def parse(self, rel_path: str, content: str, lang: str, kind: DocKind) -> ParseResult:
        lines = content.splitlines()
        nodes: list[ParseNode] = []
        start = 1
        buf = 0
        for i, line in enumerate(lines, start=1):
            if line.strip():
                buf += 1
                continue
            if buf:
                nodes.append(ParseNode(ChunkKind.BLOCK, start, i - 1))
                buf = 0
            start = i + 1
        if buf:
            nodes.append(ParseNode(ChunkKind.BLOCK, start, len(lines)))
        if not nodes and lines:
            nodes.append(ParseNode(ChunkKind.BLOCK, 1, len(lines)))
        title = next((ln.strip() for ln in lines if ln.strip()), None)
        return ParseResult(tuple(nodes), lang, kind, title=title)
