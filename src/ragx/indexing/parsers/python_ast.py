"""Parser de Python via `ast` da stdlib: AST correto, zero dependência."""

from __future__ import annotations

import ast

from ragx.core.models import ChunkKind, DocKind, ParseNode, ParseResult


class PythonParser:
    name = "python-ast"

    def parse(self, rel_path: str, content: str, lang: str, kind: DocKind) -> ParseResult:
        tree = ast.parse(content)  # SyntaxError sobe -> degrada para fallback
        lines = content.splitlines()
        nodes: list[ParseNode] = []

        preamble = _preamble(tree, lines)
        if preamble:
            nodes.append(preamble)

        for node in tree.body:
            built = _build(node, lines, prefix="")
            if built:
                nodes.append(built)

        return ParseResult(tuple(nodes), lang, kind, title=ast.get_docstring(tree))


def _start(node: ast.AST) -> int:
    """Intervalo inclui os decorators — senão o chunk perde o @property."""
    decorators = getattr(node, "decorator_list", [])
    first = min((d.lineno for d in decorators), default=None)
    return min(first, node.lineno) if first else node.lineno  # type: ignore[attr-defined]


def _preamble(tree: ast.Module, lines: list[str]) -> ParseNode | None:
    """Imports e constantes de módulo: é onde mora a informação de dependência
    que o grafo (Fase 3) consome."""
    stop = None
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.extend(_import_names(node))
            stop = node.end_lineno or node.lineno
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)):
            stop = node.end_lineno or node.lineno
        else:
            break
    if stop is None:
        return None
    return ParseNode(ChunkKind.FILE, 1, stop, symbol=None, meta={"imports": imports})


def _import_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        base = node.module or ""
        return [f"{base}.{a.name}" if base else a.name for a in node.names]
    return []


def _build(node: ast.AST, lines: list[str], prefix: str) -> ParseNode | None:
    if isinstance(node, ast.ClassDef):
        qname = f"{prefix}{node.name}"
        children = tuple(
            c
            for c in (_build(b, lines, f"{qname}.") for b in node.body)
            if c is not None
        )
        return ParseNode(
            ChunkKind.CLASS,
            _start(node),
            node.end_lineno or node.lineno,
            symbol=qname,
            children=children,
            meta={
                "bases": [ast.unparse(b) for b in node.bases],
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "docstring": ast.get_docstring(node),
            },
        )
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        qname = f"{prefix}{node.name}"
        return ParseNode(
            ChunkKind.METHOD if prefix else ChunkKind.FUNCTION,
            _start(node),
            node.end_lineno or node.lineno,
            symbol=qname,
            meta={
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "docstring": ast.get_docstring(node),
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "args": [a.arg for a in node.args.args],
            },
        )
    return None
