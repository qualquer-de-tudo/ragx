"""O "sem RAGX" do gráfico de economia: tamanho dos arquivos de onde o contexto saiu.

Soma `chunks.token_count` dos documentos-fonte, lido do índice (nunca do disco),
na MESMA unidade do que o `build_context` entrega (o contador de tokens). Antes
era `size_bytes // 4`: em markdown erra por ~30% (docs/09-mcp.md: 4.265 contra
5.993 tokens reais), e a economia aparecia em duas unidades diferentes.

Isto é um LIMITE SUPERIOR ("arquivos inteiros"), não a economia real: um agente com
Grep não leria os arquivos todos. Quem pode afirmar a economia real é o A/B da 0162.
Mora aqui, e não em `ragx.mcp`, porque é lógica, e o servidor é casca fina (ADR-0006).
"""

from __future__ import annotations

from collections.abc import Sequence

from ragx.config import Config
from ragx.storage.db import open_db


def whole_files_tokens(cfg: Config, sources: Sequence[str]) -> int:
    """Tokens dos documentos `sources` inteiros, segundo o índice. `0` se não houver índice."""
    if not sources:
        return 0
    try:
        with open_db(cfg.db_path, read_only=True) as conn:
            marks = ",".join("?" * len(sources))
            row = conn.execute(
                "SELECT COALESCE(SUM(c.token_count), 0) FROM chunks c "
                f"JOIN documents d ON d.id = c.document_id WHERE d.rel_path IN ({marks})",
                list(sources),
            ).fetchone()
    except Exception:
        return 0
    return int(row[0])
