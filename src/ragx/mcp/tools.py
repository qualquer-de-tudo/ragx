"""Contratos e implementação das ferramentas MCP.

CASCA FINA (ADR-0006): cada ferramenta é validar -> chamar serviço -> serializar.
Zero lógica de negócio, zero acesso a filesystem.

Este módulo NÃO pode importar `os`, `subprocess`, `pathlib`, `socket` nem
cliente HTTP — há teste arquitetural que falha se alguém tentar.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ragx.security.redactor import safe_echo

__all__ = ["safe_echo"]

MAX_LIMIT = 50
MAX_TOKENS = 32_000
MAX_RESPONSE_BYTES = 1_048_576

_SCOPE_PATTERN = r"^(current|all|project:[\w.\-]{1,64})$"


# ── contratos ───────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=MAX_LIMIT)
    lang: str | None = Field(default=None, max_length=32)
    kind: Literal["file", "class", "function", "method", "section", "statement", "block"] | None = None
    path_glob: str | None = Field(default=None, max_length=200)
    scope: str = Field(default="current", pattern=_SCOPE_PATTERN)


class BuildContextRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    tokens: int = Field(default=3000, ge=200, le=MAX_TOKENS)
    format: Literal["markdown", "json"] = "markdown"
    include_graph: bool = True
    scope: str = Field(default="current", pattern=_SCOPE_PATTERN)


class SearchHit(BaseModel):
    project: str  # obrigatório: conhecimento sem origem não é entregue
    chunk_id: str
    document_path: str
    symbol: str | None = None
    heading_path: str | None = None
    kind: str
    lines: tuple[int, int]
    score: float
    content: str
    matched_by: list[str] = Field(default_factory=list)


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def validate_path(value: str) -> str | None:
    """Caminho relativo já indexado. É CHAVE DE CONSULTA, nunca caminho de arquivo."""
    if not value or len(value) > 400:
        return None
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return None
    if len(normalized) > 1 and normalized[1] == ":":
        return None
    return normalized


#: Tamanho do `chunk_id` no fio. O id completo tem 32 hex; 48 bits bastam para
#: distinguir chunks de um projeto, e 20 caracteres a menos em cada hit, cada
#: fragmento e cada relação são token que o agente não paga (RAGX-0155).
WIRE_ID_LEN = 12
MIN_ID_PREFIX = 8


def wire_id(chunk_id: str) -> str:
    return chunk_id[:WIRE_ID_LEN]


def dump(payload: Any) -> str:
    """JSON compacto, com acentos como estão: é o que o cliente lê, e cada espaço
    e cada `\u00e7` é token. O SDK reindentava (`indent=2`) o `dict` e ainda o
    repetia em `structuredContent` (RAGX-0155)."""
    import json as _json

    return _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def compact(value: Any) -> Any:
    """Remove chaves de dict com valor `None`, em qualquer profundidade.

    Ausência significa `null`. Listas não perdem elementos; só os dicts dentro
    delas são limpos. `0`, `False`, `""` e `[]` NÃO são nulos e ficam.
    """
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def cap(payload: dict[str, Any], max_bytes: int = MAX_RESPONSE_BYTES) -> dict[str, Any]:
    """Resposta grande demais é recusada com orientação — nunca truncada em
    silêncio, que faria o agente acreditar que viu tudo."""
    size = len(dump(payload).encode("utf-8"))
    if size <= max_bytes:
        return payload
    return err(
        "too_large",
        f"resposta de {size} bytes excede o limite de {max_bytes}; "
        "reduza `limit` ou `tokens` e pagine",
    )
