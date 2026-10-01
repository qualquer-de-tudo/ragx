"""Contexto de validade do veredito guardado (`file_verdicts`, RAGX-0139).

O veredito de um arquivo fora do índice só vale enquanto TUDO de que o Security Gate e o
parser dependem for o mesmo. Esta função resume isso numa string; quando ela muda, o cache
inteiro é descartado e os arquivos são reavaliados. Na dúvida, não usar o cache: um veredito
velho é pior que uma releitura.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ragx.core.ids import CHUNKER_VERSION, RULESET_VERSION
from ragx.storage.db import get_meta, set_meta
from ragx.storage.repositories import VerdictRepo

META_KEY = "verdict_ctx"

#: Vereditos que o cache guarda.
BLOCKED = "blocked"
CACHED_SKIPS = frozenset({"unsupported", "binary", "undecodable"})


@lru_cache(maxsize=1)
def _rules_digest() -> str:
    """`sha256` dos arquivos de regra empacotados: `RULESET_VERSION` não tem bump confiável."""
    from ragx.security import rules as rules_pkg

    pasta = Path(rules_pkg.__file__).parent
    h = hashlib.sha256()
    for arquivo in sorted(p for p in pasta.iterdir() if p.suffix in {".yaml", ".yml", ".txt"}):
        h.update(arquivo.name.encode("utf-8"))
        h.update(arquivo.read_bytes())
    return h.hexdigest()


def verdict_context(cfg: Any) -> str:
    sec, idx = cfg.security, cfg.index
    dados = {
        "rules": _rules_digest(),
        "ruleset": RULESET_VERSION,
        "chunker": CHUNKER_VERSION,
        "security": {
            "policy": sec.policy,
            "scan_content": sec.scan_content,
            "min_entropy": sec.min_entropy,
            "disabled_rules": sorted(sec.disabled_rules),
        },
        "index": {
            "exclude": list(idx.exclude),
            "include": list(idx.include),
            "include_unknown": idx.include_unknown,
            "max_file_bytes": idx.max_file_bytes,
        },
        "base_max_file_bytes": cfg.base.max_file_bytes,
    }
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode("utf-8")).hexdigest()


def prepare(
    conn: Any, cfg: Any, *, full: bool, dry_run: bool, only: Any = None
) -> dict[str, tuple[int, int, str, str | None]]:
    """Os vereditos que esta rodada pode USAR (`{}` se o cache não vale).

    `full` e contexto diferente descartam o cache (e regravam o contexto), exceto em `dry_run`,
    que nunca escreve. `only` restringe aos caminhos pedidos (a reindexação por caminho).
    """
    repo = VerdictRepo(conn)
    atual = verdict_context(cfg)
    valido = get_meta(conn, META_KEY) == atual
    if dry_run:
        return repo.load(only) if valido and not full else {}
    if full or not valido:
        repo.clear()
        set_meta(conn, META_KEY, atual)
        return {}
    return repo.load(only)
