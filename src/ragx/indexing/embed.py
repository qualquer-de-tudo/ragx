"""Geração de embeddings dos chunks já indexados.

Etapa separada do pipeline de propósito: embedder fora do ar não pode derrubar
a indexação. Os chunks ficam gravados sem vetor e `ragx index --embed-only`
completa depois (ADR-0004).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ragx.config import Config
from ragx.embeddings import build_embedder, embedder_id
from ragx.embeddings.base import Embedder, EmbeddingCache
from ragx.indexing.chunkers import context_prefix
from ragx.storage.vectors import (
    coarse_only_count,
    embedding_count,
    has_vectors,
    pending_for_embedding,
    register_model,
    store_vectors,
)


@dataclass
class EmbedReport:
    model_id: str = ""
    pending: int = 0
    embedded: int = 0
    from_cache: int = 0
    total: int = 0
    replaced_model: int = 0
    error: str | None = None
    #: vetores int8 trazidos de `knowledge/embeddings` (RAGX-0144) e quantos ainda estão só grosseiros
    imported: int = 0
    coarse_only: int = 0
    import_warning: str | None = None


def embed_pending(
    cfg: Config,
    conn: sqlite3.Connection,
    progress: Callable[[int, int], None] | None = None,
    upgrade_coarse: bool = True,
) -> EmbedReport:
    """Embute o que falta. `upgrade_coarse` completa o float32 das linhas só-grosseiras.

    Num banco novo (o modelo ainda não tem vetor nenhum), traz ANTES os vetores versionados de
    `knowledge/embeddings` (RAGX-0144): só o que de fato falta é embutido. O `sync` passa
    `upgrade_coarse=False`: embute o arquivo novo ou editado e deixa os importados grosseiros;
    `ragx index --embed-only` completa depois.
    """
    report = EmbedReport()
    # Nome e dimensão saem da configuração: a indexação sem mudança não precisa
    # carregar o modelo (~2,85 s no fastembed) nem sondar o daemon (até 2 s no
    # Ollama) só para descobrir que não há chunk pendente (RAGX-0130).
    try:
        model_id = embedder_id(cfg)
    except Exception as exc:
        report.error = str(exc)
        return report
    dim = cfg.embedding.dim
    report.model_id = model_id
    vdim = min(cfg.embedding.versioned_dim or dim, dim)
    register_model(conn, model_id, dim, vdim, cfg.embedding.versioned_quant)

    # Vetores de modelo anterior ficam órfãos e INCOMPARÁVEIS com os novos.
    # Deixá-los no banco fez `dedupe_near` comparar 384 com 256 dimensões.
    stale = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM embedding_models WHERE id != ?", (model_id,)
        )
    ]
    if stale:
        ph = ",".join("?" * len(stale))
        n = conn.execute(
            f"DELETE FROM embeddings WHERE model_id IN ({ph})", stale
        ).rowcount
        conn.execute(f"DELETE FROM embedding_models WHERE id IN ({ph})", stale)
        conn.commit()
        report.replaced_model = n or 0

    if not has_vectors(conn, model_id):
        try:
            from ragx.sync.embeddings_import import import_embeddings

            imp = import_embeddings(cfg, conn)
            report.imported = imp.imported
            report.import_warning = imp.warning
        except Exception as exc:  # o import é um atalho: falhar nele nunca impede o caminho normal
            report.import_warning = f"embeddings versionados não importados: {exc}"

    pending = pending_for_embedding(conn, model_id, include_coarse=upgrade_coarse)
    report.pending = len(pending)
    if not pending:
        report.total = embedding_count(conn)
        report.coarse_only = coarse_only_count(conn, model_id)
        return report

    try:
        embedder = build_embedder(cfg)
    except Exception as exc:
        report.error = str(exc)
        return report

    # Sondagem barata ANTES de qualquer lote. Sem isto, numa máquina sem o daemon
    # cada indexação paga 3 retries com backoff por lote — dezenas de segundos
    # para chegar à mesma conclusão que uma checagem de 2 s dá.
    probe = getattr(embedder, "available", None)
    if probe is not None and not probe():
        report.error = (
            f"embedder {embedder.id} indisponível\n"
            "  → inicie o daemon: ollama serve\n"
            "  → ou use: ragx config set embedding.provider hashing"
        )
        return report

    with _abrir_cache(cfg, embedder.id) as cache:
        _embed_all(conn, cfg, embedder, cache, pending, vdim, report, progress)
    report.total = embedding_count(conn)
    report.coarse_only = coarse_only_count(conn, model_id)
    return report


_GIT_COMUM: dict[str, Path] = {}


def _pasta_git_comum(root: Path) -> Path | None:
    """A pasta `.git` comum aos worktrees, lida dos metadados do git SEM chamar o `git`.

    A reindexação por caminho (RAGX-0140) não pode pagar um subprocesso por edição: sobe da raiz até achar `.git`;
    pasta = repositório principal; arquivo (`gitdir: X`) = worktree, e `X/commondir` aponta a pasta comum. `None` fora
    de git ou em qualquer dúvida. Lê só arquivos de metadado do git, nunca o código do projeto. Memoizada por raiz.
    """
    chave = str(root)
    if chave in _GIT_COMUM:
        return _GIT_COMUM[chave]
    achado: Path | None = None
    try:
        for pasta in (Path(root).resolve(), *Path(root).resolve().parents):
            git = pasta / ".git"
            if git.is_dir():
                achado = git
                break
            if git.is_file():
                texto = git.read_text(encoding="utf-8", errors="replace").strip()
                if texto.startswith("gitdir:"):
                    gitdir = Path(texto[len("gitdir:"):].strip())
                    gitdir = gitdir if gitdir.is_absolute() else (pasta / gitdir)
                    comum = gitdir / "commondir"
                    if comum.is_file():
                        rel = comum.read_text(encoding="utf-8", errors="replace").strip()
                        achado = (gitdir / rel).resolve()
                    else:
                        achado = gitdir.resolve()
                break
    except OSError:
        achado = None
    if achado is not None and not achado.is_dir():
        achado = None
    if achado is not None:  # `None` não é guardado: um `git init` depois tem de ser visto
        _GIT_COMUM[chave] = achado
    return achado


def shared_cache_root(cfg: Config) -> Path:
    """Onde o cache de embedding grava (RAGX-0170).

    Num repositório git, `<pasta .git comum>/ragx/cache`: todos os worktrees do repositório compartilham o mesmo cache
    por `content_hash`, então o worktree novo não reembute o que o irmão já embutiu. Fora de git, ou se a pasta não
    puder ser descoberta, é o cache local de sempre (`<raiz>/.ragx/cache`). Não é versionado nem sai do clone.
    """
    local = cfg.state_dir / "cache"
    comum = _pasta_git_comum(cfg.root)
    return local if comum is None else comum / "ragx" / "cache"


def _abrir_cache(cfg: Config, model_id: str) -> EmbeddingCache:
    """O cache compartilhado do repositório, lendo também o local; se ele não abrir (pasta sem permissão), o local."""
    local = cfg.state_dir / "cache"
    compartilhado = shared_cache_root(cfg)
    if compartilhado != local:
        cache = EmbeddingCache(compartilhado, model_id, cfg.embedding.cache, also_read=[local])
        if cache.usable or not cfg.embedding.cache:
            return cache
        cache.close()
    return EmbeddingCache(local, model_id, cfg.embedding.cache)


#: a cada quantos lotes grava o que já foi embutido (RAGX-0146): `ragx index` morto no meio retoma do ponto em que parou
CHECKPOINT_EVERY = 10

_Row = tuple[str, str, str, str, str, str | None, str | None]


def _embed_all(
    conn: sqlite3.Connection,
    cfg: Config,
    embedder: Embedder,
    cache: EmbeddingCache,
    pending: list[_Row],
    vdim: int,
    report: EmbedReport,
    progress: Callable[[int, int], None] | None,
) -> None:
    cached = cache.get_many([row[1] for row in pending])
    todo: list[_Row] = []
    ready: list[tuple[str, np.ndarray]] = []
    for row in pending:
        vec = cached.get(row[1])
        if vec is not None and vec.size == embedder.dim:
            ready.append((row[0], vec))
            report.from_cache += 1
        else:
            todo.append(row)

    def flush() -> None:
        if ready:
            report.embedded += store_vectors(conn, embedder.id, ready, vdim)
            conn.commit()  # checkpoint: o que já foi embutido sobrevive a um processo morto
            ready.clear()

    batch = max(cfg.embedding.batch, 1)
    done = 0
    try:
        for n, i in enumerate(range(0, len(todo), batch), start=1):
            window = todo[i : i + batch]
            # Prefixo de contexto entra SÓ no embedding, nunca em chunks.content.
            texts = [
                _prefixed(rel_path, content, cid, kind, symbol, heading)
                for cid, _h, content, rel_path, kind, symbol, heading in window
            ]
            vecs = embedder.embed_documents(texts)
            cache.put_many([(row[1], vec) for row, vec in zip(window, vecs, strict=True)])
            ready.extend((row[0], vec) for row, vec in zip(window, vecs, strict=True))
            done += len(window)
            if progress:
                progress(done, len(todo))
            if n % CHECKPOINT_EVERY == 0:
                flush()
    except Exception as exc:
        report.error = str(exc)
    finally:
        flush()


def _prefixed(
    rel_path: str, content: str, chunk_id: str, kind: str, symbol: str | None, heading_path: str | None
) -> str:
    """O texto que vai ao embedder: prefixo de contexto + conteúdo, montado da linha já lida (sem `SELECT`)."""
    from ragx.core.models import Chunk, ChunkKind

    stub = Chunk(
        id=chunk_id, document_id="", ordinal=0, kind=ChunkKind(kind),
        start_line=0, end_line=0, content=content, content_hash="", token_count=0,
        symbol=symbol, heading_path=heading_path,
    )
    return context_prefix(rel_path, stub)
