"""Chunkers: transformam estrutura sintática em chunks autocontidos.

Invariantes (ADR-0005):
  1. chunk de código é uma unidade compilável ou quase
  2. bloco de código e tabela em Markdown nunca são partidos
  3. parent_id preserva a hierarquia método -> classe -> arquivo
  4. unidade acima de max_tokens é dividida por blocos lógicos, não por caractere
  5. fatiamento é determinístico
"""

from __future__ import annotations

from dataclasses import dataclass

from ragx.core.ids import CHUNKER_VERSION, chunk_id, content_hash, document_id
from ragx.core.models import Chunk, ChunkKind, DocKind, ParseNode, ParseResult
from ragx.tokens import count_tokens


@dataclass(frozen=True, slots=True)
class ChunkOptions:
    max_tokens: int = 512
    min_tokens: int = 24


def chunk_document(
    rel_path: str, content: str, parsed: ParseResult, opts: ChunkOptions | None = None
) -> list[Chunk]:
    opts = opts or ChunkOptions()
    lines = content.splitlines()
    doc_id = document_id(rel_path)
    out: list[Chunk] = []
    counter = _Counter()

    if parsed.doc_kind is DocKind.CODE:
        for node in parsed.nodes:
            _emit_code(node, None, rel_path, doc_id, lines, opts, out, counter)
    else:
        for node in parsed.nodes:
            _emit_doc(node, rel_path, doc_id, lines, opts, out, counter)

    return _dedupe_ids(_merge_tiny(out, opts, rel_path), rel_path)


class _Counter:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> int:
        i = self.n
        self.n += 1
        return i


def _slice(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[max(start - 1, 0) : end])


def _make(
    rel_path: str,
    doc_id: str,
    kind: ChunkKind,
    start: int,
    end: int,
    text: str,
    ordinal: int,
    symbol: str | None = None,
    heading_path: str | None = None,
    parent_id: str | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id(rel_path, text, CHUNKER_VERSION),
        document_id=doc_id,
        ordinal=ordinal,
        kind=kind,
        start_line=start,
        end_line=end,
        content=text,
        content_hash=content_hash(text),
        token_count=count_tokens(text),
        symbol=symbol,
        heading_path=heading_path,
        parent_id=parent_id,
    )


# ── Código: arquivo -> classe -> método ─────────────────────────────────
def _emit_code(
    node: ParseNode,
    parent_id: str | None,
    rel_path: str,
    doc_id: str,
    lines: list[str],
    opts: ChunkOptions,
    out: list[Chunk],
    counter: _Counter,
) -> None:
    if node.children:
        # Chunk de classe = cabeçalho, SEM repetir o corpo dos métodos.
        header_end = min((c.start_line for c in node.children), default=node.end_line) - 1
        header_end = max(header_end, node.start_line)
        text = _slice(lines, node.start_line, header_end)
        summary = ", ".join(c.symbol.split(".")[-1] for c in node.children if c.symbol)
        if summary:
            text = f"{text}\n# métodos: {summary}"
        chunk = _make(
            rel_path, doc_id, node.kind, node.start_line, header_end, text,
            counter.next(), node.symbol, parent_id=parent_id,
        )
        out.append(chunk)
        for child in node.children:
            _emit_code(child, chunk.id, rel_path, doc_id, lines, opts, out, counter)
        return

    text = _slice(lines, node.start_line, node.end_line)
    if count_tokens(text) <= opts.max_tokens:
        out.append(
            _make(rel_path, doc_id, node.kind, node.start_line, node.end_line, text,
                  counter.next(), node.symbol, parent_id=parent_id)
        )
        return

    # Acima do teto: divide por blocos lógicos, com sufixo #part-N.
    for i, (s, e) in enumerate(_split_logical(lines, node.start_line, node.end_line, opts), 1):
        part = _slice(lines, s, e)
        sym = f"{node.symbol}#part-{i}" if node.symbol else None
        out.append(
            _make(rel_path, doc_id, node.kind, s, e, part, counter.next(), sym,
                  parent_id=parent_id)
        )


def _split_logical(
    lines: list[str], start: int, end: int, opts: ChunkOptions
) -> list[tuple[int, int]]:
    """Corta em blocos lógicos de topo (if/for/try/while), nunca no meio de uma
    linha. Fallback: corte por acumulação de tokens."""
    spans: list[tuple[int, int]] = []
    cur_start = start
    acc = 0
    base_indent = _indent(lines[start - 1]) if start <= len(lines) else 0

    for i in range(start, min(end, len(lines)) + 1):
        line = lines[i - 1]
        acc += count_tokens(line)
        is_boundary = (
            acc >= opts.max_tokens
            and line.strip()
            and _indent(line) <= base_indent + 4
        )
        if is_boundary and i > cur_start:
            spans.append((cur_start, i - 1))
            cur_start, acc = i, 0
    if cur_start <= end:
        spans.append((cur_start, end))
    return spans or [(start, end)]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


# ── Documentação: documento -> heading -> conteúdo ──────────────────────
def _emit_doc(
    node: ParseNode,
    rel_path: str,
    doc_id: str,
    lines: list[str],
    opts: ChunkOptions,
    out: list[Chunk],
    counter: _Counter,
) -> None:
    hp = node.meta.get("heading_path") or None
    text = _slice(lines, node.start_line, node.end_line)
    if count_tokens(text) <= opts.max_tokens:
        if text.strip():
            out.append(
                _make(rel_path, doc_id, node.kind, node.start_line, node.end_line, text,
                      counter.next(), node.symbol, heading_path=hp)
            )
        return

    protected: list[tuple[int, int]] = node.meta.get("protected", [])
    for s, e in _split_paragraphs(lines, node.start_line, node.end_line, opts, protected):
        part = _slice(lines, s, e)
        if not part.strip():
            continue
        out.append(
            _make(rel_path, doc_id, node.kind, s, e, part, counter.next(), node.symbol,
                  heading_path=hp)
        )


def _split_paragraphs(
    lines: list[str],
    start: int,
    end: int,
    opts: ChunkOptions,
    protected: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Corta em linha em branco, mas NUNCA dentro de um intervalo protegido
    (bloco de código, tabela)."""

    def guarded(i: int) -> bool:
        return any(a <= i <= b for a, b in protected)

    spans: list[tuple[int, int]] = []
    cur = start
    acc = 0
    for i in range(start, min(end, len(lines)) + 1):
        acc += count_tokens(lines[i - 1])
        if acc >= opts.max_tokens and not lines[i - 1].strip() and not guarded(i):
            spans.append((cur, i))
            cur, acc = i + 1, 0
    if cur <= end:
        spans.append((cur, end))
    return spans or [(start, end)]


# ── Fusão de chunks minúsculos ──────────────────────────────────────────
def _merge_tiny(chunks: list[Chunk], opts: ChunkOptions, rel_path: str) -> list[Chunk]:
    """Getters triviais viram um chunk só, em vez de dezenas de 3 linhas."""
    if not chunks:
        return chunks
    out: list[Chunk] = []
    for c in chunks:
        if (
            out
            and c.token_count < opts.min_tokens
            and out[-1].token_count < opts.max_tokens
            and out[-1].parent_id == c.parent_id
            and out[-1].kind == c.kind
            and out[-1].end_line + 2 >= c.start_line
        ):
            prev = out[-1]
            text = f"{prev.content}\n{c.content}"
            out[-1] = Chunk(
                # O id acompanha o conteúdo. Manter o id anterior depois de
                # alterar o texto quebraria a correspondência id <-> content_hash,
                # e a reidratação (Fase 9) passaria a divergir em silêncio.
                id=chunk_id(rel_path, text, CHUNKER_VERSION),
                document_id=prev.document_id,
                ordinal=prev.ordinal,
                kind=prev.kind,
                start_line=prev.start_line,
                end_line=c.end_line,
                content=text,
                content_hash=content_hash(text),
                token_count=count_tokens(text),
                symbol=prev.symbol,
                heading_path=prev.heading_path,
                parent_id=prev.parent_id,
            )
            continue
        out.append(c)
    # renumera e recalcula IDs afetados pela fusão
    return [
        Chunk(
            id=c.id, document_id=c.document_id, ordinal=i, kind=c.kind,
            parent_id=c.parent_id, symbol=c.symbol, heading_path=c.heading_path,
            start_line=c.start_line, end_line=c.end_line, content=c.content,
            content_hash=c.content_hash, token_count=c.token_count,
        )
        for i, c in enumerate(out)
    ]


def context_prefix(rel_path: str, chunk: Chunk) -> str:
    """Prefixo usado só na geração do embedding — nunca gravado em chunks.content."""
    parts = [rel_path]
    if chunk.heading_path:
        parts.append(chunk.heading_path)
    elif chunk.symbol:
        parts.append(f"{chunk.kind.value} {chunk.symbol}")
    return f"[{' › '.join(parts)}]\n{chunk.content}"


def _dedupe_ids(chunks: list[Chunk], rel_path: str) -> list[Chunk]:
    """Garante id único dentro do documento.

    Conteúdo byte-idêntico em dois pontos do mesmo arquivo (dois helpers iguais,
    duas seções repetidas) produziria o mesmo id, violando a PK. A primeira
    ocorrência mantém o id puro — o caso comum continua estável entre execuções;
    as seguintes recebem um sufixo determinístico, preservando o intervalo de
    linhas de cada uma.
    """
    seen: dict[str, int] = {}
    out: list[Chunk] = []
    for c in chunks:
        n = seen.get(c.id, 0)
        seen[c.id] = n + 1
        if n == 0:
            out.append(c)
            continue
        out.append(
            Chunk(
                id=chunk_id(rel_path, f"{c.content}::ragx-dup-{n}::", CHUNKER_VERSION),
                document_id=c.document_id, ordinal=c.ordinal, kind=c.kind,
                parent_id=c.parent_id, symbol=c.symbol, heading_path=c.heading_path,
                start_line=c.start_line, end_line=c.end_line, content=c.content,
                content_hash=c.content_hash, token_count=c.token_count,
            )
        )
    return out
