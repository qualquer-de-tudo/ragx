"""IDs determinísticos.

Requisito duro: mesmo input + mesma versão do chunker = mesmo ID, em qualquer
máquina e qualquer sistema operacional. Sem isso não existe indexação incremental,
nem merge no Git, nem reidratação.

Ver docs/03-modelo-de-dados.md.
"""

from __future__ import annotations

import hashlib
import unicodedata

CHUNKER_VERSION = "1"
"""Versão do fatiamento. Bump obrigatório em QUALQUER mudança de chunking:
muda todos os IDs de propósito, forçando reindexação em vez de corromper o índice."""

SCHEMA_VERSION = 5
RULESET_VERSION = "builtin@1"

_ID_LEN = 32


def normalize_text(text: str) -> str:
    """Normaliza conteúdo antes de hashear.

    1. CRLF/CR -> LF (senão Windows e Linux produzem IDs diferentes)
    2. remove trailing whitespace por linha
    3. remove newlines nas bordas
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip("\n")


def normalize_path(rel_path: str) -> str:
    """Caminho relativo, sempre POSIX, sempre NFC.

    Caminho absoluto no ID vazaria o nome do usuário no pacote exportado, então
    é erro e não normalização silenciosa.
    """
    p = unicodedata.normalize("NFC", rel_path.replace("\\", "/"))
    # A verificação vem ANTES de qualquer strip — senão "/home/x" viraria "home/x"
    # e o caminho absoluto passaria despercebido.
    if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        raise ValueError(f"caminho absoluto não pode compor um ID: {rel_path!r}")
    while p.startswith("./"):
        p = p[2:]
    return p


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:_ID_LEN]


def content_hash(content: str) -> str:
    """Hash do conteúdo normalizado. Base da detecção de mudança e da reidratação."""
    return hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()


def document_id(rel_path: str) -> str:
    """A identidade do documento é o caminho — conteúdo vive em content_hash."""
    return _digest(normalize_path(rel_path))


def chunk_id(rel_path: str, content: str, chunker_version: str = CHUNKER_VERSION) -> str:
    return _digest(normalize_path(rel_path), normalize_text(content), chunker_version)


def entity_id(entity_type: str, qualified_name: str) -> str:
    return _digest(entity_type, qualified_name)


def relation_id(src_id: str, rel_type: str, dst_id: str) -> str:
    return _digest(src_id, rel_type, dst_id)


def shard_of(item_id: str, shards: int) -> str:
    """Shard por PREFIXO do ID (não por ordem de inserção).

    É isso que mantém o diff do Git pequeno: um item novo cai sempre no mesmo
    shard, e os demais ficam byte-idênticos. Ver docs/16-orcamento-de-tamanho.md.
    """
    return f"{int(item_id[:8], 16) % shards:02x}"
