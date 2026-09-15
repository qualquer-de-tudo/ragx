"""Redactor — o valor do segredo nunca é persistido, logado ou impresso.

Ver docs/02-seguranca.md. O que sobrevive é digest (para deduplicar) e um
preview mascarado (para o humano reconhecer sem revelar).
"""

from __future__ import annotations

import hashlib

from ragx.security.entropy import looks_random

PLACEHOLDER = "«RAGX:REDACTED:{rule_id}»"
_SHORT = "«curto»"
_MIN_PREVIEWABLE = 16


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def preview(value: str) -> str:
    """4 primeiros + 4 últimos. Abaixo de 16 chars não revela nada."""
    if len(value) < _MIN_PREVIEWABLE:
        return _SHORT
    return f"{value[:4]}…{value[-4:]}"


def redact_line(line: str, value: str, rule_id: str) -> str:
    """Substitui o valor no texto. Preserva o número de linhas — deslocar
    start_line/end_line quebraria a reidratação."""
    return line.replace(value, PLACEHOLDER.format(rule_id=rule_id))


def redact_all(content: str, values: list[tuple[str, str]]) -> str:
    """values: [(valor, rule_id)]. Maiores primeiro, para que um segredo que
    contenha outro não deixe resto."""
    for value, rule_id in sorted(values, key=lambda v: -len(v[0])):
        content = content.replace(value, PLACEHOLDER.format(rule_id=rule_id))
    return content


def safe_echo(value: str, max_len: int = 96) -> str:
    """Devolve ao chamador uma versão segura da entrada dele.

    Um agente que manda a chave da AWS como query receberia a chave de volta —
    na mensagem de `not_found`, no cabeçalho do contexto, no log do MCP e no
    próprio transcript. Caminho e nome de seção têm entropia baixa e passam
    inteiros; valor que parece aleatório volta mascarado.
    """
    if not value:
        return ""
    if looks_random(value, min_entropy=3.0, min_length=12):
        return preview(value)
    # Uma query longa pode conter um segredo no meio: mascara token a token.
    if len(value) > max_len or " " in value:
        partes = [
            preview(tok) if looks_random(tok, 3.0, 12) else tok
            for tok in value.split(" ")
        ]
        value = " ".join(partes)
    return value[:max_len] + ("…" if len(value) > max_len else "")
