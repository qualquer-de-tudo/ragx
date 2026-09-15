"""Compressão extrativa e determinística.

Nada de resumo gerado por LLM no MVP: resumo alucinado dentro do contexto é
pior que contexto truncado. As quatro estratégias são aplicadas em ordem, até
caber no alvo.

Invariante: a FONTE nunca é perdida. Todo trecho, comprimido ou não, mantém o
caminho e o intervalo de linhas.

Ver docs/07-context-engine.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ragx.tokens import count_tokens

_LICENSE = re.compile(
    r"^\s*(?:#|//|\*|/\*)\s*(?:copyright|licensed under|SPDX-License|all rights reserved)",
    re.IGNORECASE,
)
_GENERATED = re.compile(
    r"^\s*(?:#|//|<!--)\s*(?:auto-?generated|do not edit|@generated)", re.IGNORECASE
)
_IMPORT = re.compile(r"^\s*(?:import\s|from\s+\S+\s+import\s|use\s+\S+;|require\()")
_DEF = re.compile(
    r"^\s*(?:(?:async\s+)?def\s|class\s|function\s|public\s|private\s|protected\s|"
    r"export\s|const\s+\w+\s*=\s*(?:async\s*)?\(|@)"
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)

TRUNCATED = "…(truncado)"


@dataclass(frozen=True, slots=True)
class Compressed:
    text: str
    compressed: bool
    strategy: str
    saved_tokens: int


def compress(
    content: str,
    target_tokens: int,
    query: str = "",
    is_code: bool = False,
    keep_signature: bool = True,
) -> Compressed:
    original = count_tokens(content)
    if original <= target_tokens:
        return Compressed(content, False, "none", 0)

    text = _prune_noise(content, is_code)
    if count_tokens(text) <= target_tokens:
        return Compressed(text, True, "prune", original - count_tokens(text))

    if is_code:
        collapsed = _collapse_body(text, keep_signature=keep_signature)
        if count_tokens(collapsed) <= target_tokens:
            return Compressed(collapsed, True, "collapse", original - count_tokens(collapsed))
        text = collapsed
    else:
        picked = _select_sentences(text, target_tokens, query)
        if count_tokens(picked) <= target_tokens:
            return Compressed(picked, True, "sentences", original - count_tokens(picked))
        text = picked

    truncated = _truncate(text, target_tokens)
    return Compressed(truncated, True, "truncate", original - count_tokens(truncated))


# ── 1. poda de ruído ────────────────────────────────────────────────────
def _prune_noise(content: str, is_code: bool) -> str:
    out: list[str] = []
    blank = 0
    for line in content.splitlines():
        if _LICENSE.match(line) or _GENERATED.match(line):
            continue
        if is_code and _IMPORT.match(line):
            continue
        if not line.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(line)
    return "\n".join(out).strip("\n")


# ── 2. colapso de corpo ─────────────────────────────────────────────────
def _collapse_body(content: str, keep_signature: bool = True) -> str:
    """Mantém assinatura e docstring; substitui o corpo por uma marca.

    A assinatura NUNCA é removida — sem ela o fragmento deixa de ser citável.
    """
    lines = content.splitlines()
    if not lines:
        return content

    head: list[str] = []
    i = 0
    while i < len(lines) and (not lines[i].strip() or _DEF.match(lines[i])):
        head.append(lines[i])
        i += 1
    if not head and keep_signature:
        head = [lines[0]]
        i = 1

    # docstring logo após a assinatura
    doc: list[str] = []
    if i < len(lines):
        stripped = lines[i].strip()
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                doc.append(lines[i])
                if not (stripped.endswith(quote) and len(stripped) > len(quote)):
                    i += 1
                    while i < len(lines):
                        doc.append(lines[i])
                        if quote in lines[i]:
                            break
                        i += 1
                i += 1
                break

    remaining = len(lines) - i
    if remaining <= 2:
        return content
    body = f"    # ... ({remaining} linhas omitidas)"
    return "\n".join([*head, *doc, body])


# ── 3. seleção de sentenças ─────────────────────────────────────────────
def _select_sentences(content: str, target_tokens: int, query: str) -> str:
    """Mantém as sentenças mais próximas da query — e SEMPRE a primeira, que
    carrega o tema da seção."""
    lines = content.splitlines()
    heading = lines[0] if lines and lines[0].lstrip().startswith("#") else ""
    body = "\n".join(lines[1:]) if heading else content

    sentences = [s.strip() for s in _SENTENCE.split(body) if s.strip()]
    if len(sentences) <= 1:
        return content

    q_terms = {w.lower() for w in _WORD.findall(query)}
    scored: list[tuple[float, int, str]] = []
    for idx, s in enumerate(sentences):
        terms = {w.lower() for w in _WORD.findall(s)}
        overlap = len(terms & q_terms) / max(len(q_terms), 1) if q_terms else 0.0
        first_bonus = 0.5 if idx == 0 else 0.0
        scored.append((overlap + first_bonus, idx, s))

    scored.sort(key=lambda t: -t[0])
    picked: list[tuple[int, str]] = []
    used = count_tokens(heading)
    for _score, idx, s in scored:
        cost = count_tokens(s)
        if used + cost > target_tokens and picked:
            break
        picked.append((idx, s))
        used += cost

    picked.sort(key=lambda t: t[0])
    parts = [heading] if heading else []
    parts.append(" ".join(s for _i, s in picked))
    return "\n".join(p for p in parts if p).strip()


# ── 4. truncamento marcado ──────────────────────────────────────────────
def _truncate(content: str, target_tokens: int) -> str:
    lines = content.splitlines()
    out: list[str] = []
    used = count_tokens(TRUNCATED)
    for line in lines:
        cost = count_tokens(line)
        if used + cost > target_tokens:
            break
        out.append(line)
        used += cost
    if not out and lines:
        out = [lines[0][: max(target_tokens * 3, 40)]]
    return "\n".join([*out, TRUNCATED])
