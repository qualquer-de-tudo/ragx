"""Importa os embeddings versionados de `knowledge/embeddings/` para um banco novo (RAGX-0144).

O projeto versiona o vetor int8 de cada chunk justamente para que um clone responda buscas sem
recalcular nada, mas `serialize.read_embeddings` não tinha nenhum chamador: num clone novo, o
primeiro `ragx index` reembedava todos os chunks. Este módulo faz o caminho de volta.

Regras (a segurança deste caminho é a mesma da indexação: nada de conteúdo entra por aqui):

- **Só o mesmo modelo.** O manifesto precisa citar `embedder_id(cfg)` e a mesma `versioned_dim`; senão
  nada é importado (e nada é apagado). `embed_pending` apaga os vetores de qualquer modelo diferente
  do atual na rodada seguinte, então importar de outro modelo seria desfeito.
- **Só chunk que existe.** Cada linha precisa ter `chunk_id` em `chunks`: o chunk já passou pelo
  Security Gate na indexação. Um shard que cita o chunk de um arquivo hoje bloqueado ou apagado não
  grava nada, e a contagem de `embeddings` nunca passa a de `chunks`.
- **Só vetor válido.** `versioned_dim` bytes, escala e deslocamento finitos. O int8 entra como veio
  (já truncado e renormalizado por `serialize`): não renormaliza duas vezes.
- **Nunca sobrescreve.** `INSERT OR IGNORE`: um vetor completo (float32) que o banco já tem fica.
- **Um shard por vez**, sem montar os 6,5 mil vetores (ou os 100 mil) na memória.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from ragx.config import Config
from ragx.embeddings import embedder_id
from ragx.storage.db import utcnow
from ragx.storage.vectors import register_model
from ragx.sync import serialize

_LOTE = 1000


@dataclass
class ImportReport:
    imported: int = 0
    skipped_model: int = 0
    skipped_unknown_chunk: int = 0
    skipped_bad: int = 0
    model: str | None = None
    warning: str | None = None


def import_embeddings(
    cfg: Config, conn: sqlite3.Connection, out_dir: str = "knowledge"
) -> ImportReport:
    report = ImportReport()
    meta = serialize.read_embedding_manifest(cfg, out_dir)
    if meta is None:
        return report
    report.model = str(meta.get("model"))
    declarado = _inteiro(meta.get("count"))

    try:
        model_id = embedder_id(cfg)
    except Exception as exc:  # provider desconhecido: quem indexa já reporta
        report.skipped_model = declarado
        report.warning = f"embeddings versionados não importados: {exc}"
        return report

    dim = cfg.embedding.dim
    vdim = min(cfg.embedding.versioned_dim or dim, dim)
    if meta.get("model") != model_id or _inteiro(meta.get("versioned_dim")) != vdim:
        report.skipped_model = declarado
        report.warning = (
            f"embeddings versionados são de {meta.get('model')} (int8@{meta.get('versioned_dim')}) "
            f"e a configuração pede {model_id} (int8@{vdim}): nada foi importado"
        )
        return report

    register_model(conn, model_id, dim, vdim, cfg.embedding.versioned_quant)
    existentes = {r[0] for r in conn.execute("SELECT id FROM chunks")}
    agora = utcnow()
    lote: list[tuple[str, str, None, bytes, float, float, str]] = []

    def gravar() -> None:
        if not lote:
            return
        # `rowcount` conta só as linhas inseridas (o gatilho de `vec_gen` também mexe em `meta`,
        # e `conn.total_changes` contaria essas)
        cur = conn.executemany(
            """INSERT OR IGNORE INTO embeddings
               (chunk_id, model_id, vector, vector_q, q_scale, q_offset, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            lote,
        )
        report.imported += max(cur.rowcount, 0)
        lote.clear()

    for shard in serialize.iter_embedding_shards(cfg, out_dir):
        report.skipped_bad += shard.bad
        for chunk_id, vec, scale, offset in shard.items:
            if chunk_id not in existentes:
                report.skipped_unknown_chunk += 1
            elif len(vec) != vdim or not (math.isfinite(scale) and math.isfinite(offset)):
                report.skipped_bad += 1
            else:
                lote.append((chunk_id, model_id, None, vec, scale, offset, agora))
                if len(lote) >= _LOTE:
                    gravar()
        gravar()
    conn.commit()
    return report


def _inteiro(valor: object) -> int:
    try:
        return int(valor)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0
