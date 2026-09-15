"""Busca keyword sobre FTS5/BM25.

Input do usuário NUNCA é interpretado como sintaxe FTS5 sem --raw: aspas e
operadores são escapados. Ver docs/05-busca.md.
"""

from __future__ import annotations

import re
import sqlite3

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[\wÀ-ɏ]+", re.UNICODE)
_FTS_OPERATORS = {"AND", "OR", "NOT", "NEAR"}

# Casar no NOME do símbolo vale muito mais que casar no corpo.
BM25_WEIGHTS = (1.0, 4.0, 2.0)  # content, symbol, heading_path


def split_identifier(token: str) -> list[str]:
    """AuthService -> [auth, service];  auth_service -> [auth, service]."""
    parts = [p for p in re.split(r"[_\-.]+", token) if p]
    out: list[str] = []
    for p in parts:
        out.extend(x for x in _CAMEL.split(p) if x)
    return [o.lower() for o in out if len(o) > 1]


def prepare_query(text: str, raw: bool = False) -> str:
    if raw:
        return text
    tokens = _WORD.findall(text)
    if not tokens:
        return '""'

    terms: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        low = tok.lower()
        if low in seen:
            continue
        seen.add(low)
        terms.append(f'"{low}"')
        # CamelCase/snake_case: é o que faz "auth service" achar AuthService
        for part in split_identifier(tok):
            if part not in seen:
                seen.add(part)
                terms.append(f'"{part}"')

    if terms:
        last = terms[-1][:-1] + '"*' if len(terms[-1]) > 3 else terms[-1]
        terms[-1] = last
    return " OR ".join(terms)


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 30,
    raw: bool = False,
    lang: str | None = None,
    kind: str | None = None,
    path_glob: str | None = None,
) -> list[tuple[str, float]]:
    match = prepare_query(query, raw=raw)
    w = BM25_WEIGHTS
    sql = f"""
        SELECT c.id AS cid, bm25(chunks_fts, {w[0]}, {w[1]}, {w[2]}) AS score
        FROM chunks_fts
        JOIN chunks c ON c.rowid = chunks_fts.rowid
        JOIN documents d ON d.id = c.document_id
        WHERE chunks_fts MATCH ?
    """
    args: list[object] = [match]
    if lang:
        sql += " AND d.lang = ?"
        args.append(lang)
    if kind:
        sql += " AND c.kind = ?"
        args.append(kind)
    if path_glob:
        sql += " AND d.rel_path LIKE ?"
        args.append(path_glob.replace("*", "%"))
    sql += " ORDER BY score LIMIT ?"
    args.append(limit)

    try:
        rows = conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []  # query malformada mesmo após escape: nenhum resultado, sem crash
    # bm25 devolve valores negativos (quanto menor, melhor); invertemos.
    return [(r["cid"], -float(r["score"])) for r in rows]
