"""Orçamento de tamanho — o teto do Git como restrição que o sistema faz cumprir.

Ao projetar estouro, a gravação é RECUSADA. Truncar silenciosamente produziria
um índice incompleto que ninguém perceberia. Ver docs/16-orcamento-de-tamanho.md.
"""

from __future__ import annotations

from typing import Any

from ragx.config import Config
from ragx.core.errors import BudgetExceededError

# Custo médio observado por chunk, usado na projeção antes de gravar.
BYTES_PER_CHUNK_META = 180


class Budget:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.limits = cfg.size

    # ── medição ──────────────────────────────────────────────────────────
    def report(self) -> dict[str, Any]:
        kdir = self.cfg.knowledge_dir
        cats: dict[str, dict[str, int]] = {}
        total = files = 0
        largest = {"path": "", "bytes": 0}
        oversized: list[str] = []

        if kdir.is_dir():
            for p in sorted(kdir.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(kdir)
                cat = rel.parts[0] if len(rel.parts) > 1 else "raiz"
                n = p.stat().st_size
                c = cats.setdefault(cat, {"files": 0, "bytes": 0})
                c["files"] += 1
                c["bytes"] += n
                total += n
                files += 1
                if n > largest["bytes"]:
                    largest = {"path": rel.as_posix(), "bytes": n}
                if n > self.limits.max_artifact_bytes:
                    oversized.append(rel.as_posix())

        warnings: list[str] = []
        if total > self.limits.warn_total_bytes:
            warnings.append(
                f"knowledge/ passou de {_mb(self.limits.warn_total_bytes)} "
                f"({_mb(total)}) — revise o que está sendo indexado"
            )
        for o in oversized:
            warnings.append(
                f"{o} passa de max_artifact_bytes ({_mb(self.limits.max_artifact_bytes)}) "
                "— aumente o número de shards"
            )

        return {
            "categories": cats,
            "files": files,
            "bytes": total,
            "largest": largest if largest["path"] else None,
            "oversized": oversized,
            "warn_limit": self.limits.warn_total_bytes,
            "fail_limit": self.limits.fail_total_bytes,
            "artifact_limit": self.limits.max_artifact_bytes,
            "pct_of_warn": 100.0 * total / max(self.limits.warn_total_bytes, 1),
            "exceeded": total > self.limits.fail_total_bytes,
            "warnings": warnings,
            "suggestions": self._suggestions(),
        }

    # ── projeção: chamada ANTES de gravar ────────────────────────────────
    def project(self, chunks: int, versioned_dim: int) -> int:
        """Bytes projetados de knowledge/ para N chunks."""
        per_chunk = BYTES_PER_CHUNK_META + max(versioned_dim, 0)
        graph_and_dict = int(chunks * 60)  # entidades, relações, dicionário
        return chunks * per_chunk + graph_and_dict

    def enforce(
        self, chunks: int, versioned_dim: int, contributors: dict[str, int] | None = None
    ) -> None:
        """Recusa a gravação se a projeção estourar. Nunca trunca."""
        if chunks > self.limits.max_chunks:
            raise BudgetExceededError(
                f"{chunks:,} chunks excede size.max_chunks ({self.limits.max_chunks:,}).\n"
                + self._render_suggestions(contributors)
            )
        projected = self.project(chunks, versioned_dim)
        if projected > self.limits.fail_total_bytes:
            raise BudgetExceededError(
                f"projeção {_mb(projected)} excede fail_total_bytes "
                f"({_mb(self.limits.fail_total_bytes)}). Nada foi gravado.\n"
                + self._render_suggestions(contributors)
            )

    def _suggestions(self) -> list[str]:
        return [
            "adicione os diretórios mais pesados ao .ragignore",
            "reduza a dimensão versionada: [embedding] versioned_dim = 128",
            f"eleve o teto: [size] fail_total_bytes = {self.limits.fail_total_bytes * 2}",
        ]

    def _render_suggestions(self, contributors: dict[str, int] | None) -> str:
        out = []
        if contributors:
            out.append("\n  Maiores contribuintes:")
            for path, n in sorted(contributors.items(), key=lambda kv: -kv[1])[:5]:
                out.append(f"    {path:<28} {n:>8,} chunks")
        out.append("\n  Sugestões:")
        for i, s in enumerate(self._suggestions(), 1):
            out.append(f"    {i}. {s}")
        return "\n".join(out)


def _mb(n: int) -> str:
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"
