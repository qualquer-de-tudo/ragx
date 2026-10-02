from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project, status

pytestmark = pytest.mark.integration


# O próprio ragx.toml também é indexado (.toml está na lista suportada).
N_DOCS = 4


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        # provider determinístico: testes de pipeline não podem depender de daemon
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "a.py").write_text(
        "import os\n\n\nclass A:\n    def m(self):\n        return os.name\n", encoding="utf-8"
    )
    (tmp_path / "src" / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "docs" / "d.md").write_text("# T\n\n## S\n\ntexto\n", encoding="utf-8")
    return tmp_path


def test_indexa_e_conta(proj: Path) -> None:
    cfg = load_config(proj)
    r = index_project(cfg)
    assert r.stats.indexed == N_DOCS
    assert r.new_documents == N_DOCS
    assert r.new_chunks > 0
    assert status(cfg)["documents"] == N_DOCS


def test_segunda_execucao_nao_recria_nada(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    r2 = index_project(cfg)
    assert r2.new_documents == 0
    assert r2.new_chunks == 0
    assert r2.stats.unchanged == N_DOCS


def test_modificacao_reindexa_so_o_arquivo(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    r = index_project(cfg)
    assert r.modified_documents == 1 and r.new_documents == 0
    assert r.stats.unchanged == N_DOCS - 1


def test_mudanca_so_de_indentacao_final_nao_gera_chunk_novo(proj: Path) -> None:
    """A normalização de ID remove trailing whitespace — commit de formatação
    não pode sujar o índice."""
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").write_text("def f():   \n    return 1\t\n", encoding="utf-8")
    r = index_project(cfg)
    assert r.new_chunks == 0, "trailing whitespace não pode gerar chunk novo"


def test_arquivo_removido_some_do_indice(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").unlink()
    r = index_project(cfg)
    assert r.stats.removed == 1
    assert status(cfg)["documents"] == N_DOCS - 1


def test_delete_em_cascata_nao_deixa_orfao(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "a.py").unlink()
    index_project(cfg)
    conn = sqlite3.connect(cfg.db_path)
    orfaos = conn.execute(
        "SELECT COUNT(*) FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
        "WHERE d.id IS NULL"
    ).fetchone()[0]
    fts = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert orfaos == 0
    assert fts == n, "índice FTS dessincronizado dos chunks"


def test_full_reindexa_tudo(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    r = index_project(cfg, full=True)
    assert r.stats.indexed == N_DOCS and r.stats.unchanged == 0


def test_dry_run_nao_escreve(proj: Path) -> None:
    cfg = load_config(proj)
    r = index_project(cfg, dry_run=True)
    assert r.stats.indexed == N_DOCS
    assert not cfg.db_path.exists() or status(cfg).get("documents", 0) == 0


def test_arquivo_que_vira_sensivel_e_removido(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    assert status(cfg)["documents"] == N_DOCS
    (proj / "src" / "b.py").write_text(
        'KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8"
    )
    r = index_project(cfg)
    assert r.stats.blocked == 1
    assert status(cfg)["documents"] == N_DOCS - 1


def test_run_e_registrado(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    run = status(cfg)["last_run"]
    assert run and run["mode"] == "incremental" and run["finished_at"]


def test_excecao_real_propaga_e_fica_registrada_como_erro(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão: o `finally` de `_index_once` só sabia gravar `error` para
    Ctrl+C (`report.interrupted`) — qualquer outra exceção media o laço
    quebrava para fora e a corrida ficava registrada como limpa
    (`error=None`), contando depois como "última indexação útil"."""
    from ragx.indexing import pipeline
    from ragx.storage.db import open_db

    cfg = load_config(proj)

    def _boom(*a: object, **kw: object) -> None:
        raise ValueError("falha simulada no meio do laco")

    monkeypatch.setattr(pipeline, "chunk_document", _boom)
    with pytest.raises(ValueError, match="falha simulada"):
        index_project(cfg)

    with open_db(cfg.db_path) as conn:
        row = conn.execute(
            "SELECT error, finished_at FROM index_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["finished_at"] is not None
    assert row["error"] is not None and "falha simulada" in row["error"]

    # a corrida quebrada não pode ser escolhida como "última indexação útil"
    fr = status(cfg)["freshness"]
    assert fr["state"] == "unknown"


def test_acentuacao_casa_no_fts(proj: Path) -> None:
    (proj / "docs" / "acento.md").write_text(
        "# Autenticação\n\nO fluxo de autenticação usa SSO.\n", encoding="utf-8"
    )
    cfg = load_config(proj)
    index_project(cfg)
    conn = sqlite3.connect(cfg.db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", ("autenticacao",)
    ).fetchone()[0]
    conn.close()
    assert n > 0, "remove_diacritics não está ativo"


# ── RAGX-0130: indexação sem mudança é barata ───────────────────────────
def _git_repo(raiz: Path) -> None:
    import subprocess

    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=raiz).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=raiz, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=raiz, check=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "commit", "-qm", "c1"], cwd=raiz, check=True)


def test_indexacao_sem_mudanca_nao_constroi_o_embedder(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.embeddings as emb

    cfg = load_config(proj)
    index_project(cfg)
    emb.reset_embedder_cache()
    construcoes: list[str] = []
    original = emb._construir

    def espia(c):  # type: ignore[no-untyped-def]
        construcoes.append(c.embedding.provider)
        return original(c)

    monkeypatch.setattr(emb, "_construir", espia)
    r = index_project(cfg)
    assert r.new_chunks == 0
    assert construcoes == []
    assert r.embed_error is None
    emb.reset_embedder_cache()


def test_nada_pendente_nao_falha_com_embedder_indisponivel(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama fora do ar e nenhum chunk pendente: não é erro (antes era)."""
    import ragx.embeddings as emb

    cfg = load_config(proj)
    index_project(cfg)
    emb.reset_embedder_cache()

    def quebra(c):  # type: ignore[no-untyped-def]
        raise RuntimeError("daemon fora do ar")

    monkeypatch.setattr(emb, "_construir", quebra)
    assert index_project(cfg).embed_error is None
    emb.reset_embedder_cache()


def test_com_chunk_pendente_e_embedder_fora_do_ar_o_erro_continua(proj: Path) -> None:
    import ragx.embeddings as emb

    emb.reset_embedder_cache()
    toml = (proj / "ragx.toml").read_text(encoding="utf-8").replace(
        'provider = "hashing"', 'provider = "ollama"\nbase_url = "http://127.0.0.1:9"'
    )
    (proj / "ragx.toml").write_text(toml, encoding="utf-8")
    r = index_project(load_config(proj))
    assert r.new_chunks > 0
    assert r.embed_error and "indispon" in r.embed_error
    emb.reset_embedder_cache()


def test_indexacao_sem_mudanca_chama_o_git_no_maximo_duas_vezes(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.gitinfo as gi
    from ragx import githooks

    _git_repo(proj)
    cfg = load_config(proj)
    index_project(cfg)
    chamadas: list[tuple[str, ...]] = []
    original = gi.run_quiet

    def espia(cmd, *a, **k):  # type: ignore[no-untyped-def]
        chamadas.append(tuple(cmd))
        return original(cmd, *a, **k)

    monkeypatch.setattr(gi, "run_quiet", espia)
    index_project(cfg)
    assert len(chamadas) <= 2, chamadas
    assert githooks  # a importação é parte do caminho medido


# ── RAGX-0133: arquivo ilegível agora não é arquivo removido ────────────
def _doc_e_chunks(raiz: Path, rel: str) -> tuple[int, int]:
    cfg = load_config(raiz)
    conn = sqlite3.connect(cfg.db_path)
    try:
        docs = conn.execute("SELECT COUNT(*) FROM documents WHERE rel_path = ?", (rel,)).fetchone()[0]
        chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id IN "
            "(SELECT id FROM documents WHERE rel_path = ?)", (rel,)
        ).fetchone()[0]
    finally:
        conn.close()
    return docs, chunks


def test_arquivo_travado_na_leitura_nao_some_do_indice(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    antes = _doc_e_chunks(proj, "src/b.py")
    assert antes[0] == 1 and antes[1] > 0

    original = Path.read_bytes

    def trava(self: Path) -> bytes:
        if self.name == "b.py":
            raise PermissionError(32, "violação de compartilhamento")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", trava)
    r = index_project(cfg, full=True)
    assert r.stats.removed == 0
    assert r.unreadable == 1
    assert r.stats.skip_reasons.get("unreadable") == 1
    assert _doc_e_chunks(proj, "src/b.py") == antes

    # liberado e inalterado: volta a contar como já indexado, sem reindexar
    monkeypatch.setattr(Path, "read_bytes", original)
    r2 = index_project(cfg)
    assert r2.unreadable == 0 and r2.stats.removed == 0 and r2.new_chunks == 0


def test_travado_no_stat_tambem_nao_remove(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O `stat` do walker falha DEPOIS de a listagem já ter visto o arquivo (é a
    corrida real: o antivírus pega o arquivo entre as duas chamadas). A listagem
    é substituída por uma que não faz `stat`, para isolar o do walker."""
    import os

    import ragx.walk as walk

    cfg = load_config(proj)
    index_project(cfg)
    antes = _doc_e_chunks(proj, "src/a.py")

    def lista_sem_stat(root, follow_symlinks, visited, can_prune=None, on_unreadable_dir=None):  # type: ignore[no-untyped-def]
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d != ".ragx"]
            for f in sorted(fn):
                yield Path(dp) / f

    original = Path.stat

    def stat_negado(self: Path, *a: object, **k: object):  # type: ignore[no-untyped-def]
        if self.name == "a.py":
            raise PermissionError(5, "acesso negado")
        return original(self, *a, **k)

    monkeypatch.setattr(walk, "_walk", lista_sem_stat)
    monkeypatch.setattr(Path, "stat", stat_negado)
    r = index_project(cfg)
    assert r.stats.removed == 0 and r.unreadable == 1
    assert _doc_e_chunks(proj, "src/a.py") == antes


def test_pasta_ilegivel_nao_apaga_o_que_estava_sob_ela(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    antes = _doc_e_chunks(proj, "src/a.py")
    original = Path.iterdir

    def iterdir_negado(self: Path):  # type: ignore[no-untyped-def]
        if self.name == "src":
            raise PermissionError(5, "acesso negado")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", iterdir_negado)
    r = index_project(cfg)
    assert r.stats.removed == 0
    assert _doc_e_chunks(proj, "src/a.py") == antes


def test_arquivo_realmente_apagado_continua_saindo_do_indice(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "src" / "b.py").unlink()
    r = index_project(cfg)
    assert r.stats.removed == 1 and r.unreadable == 0
    assert _doc_e_chunks(proj, "src/b.py") == (0, 0)


# ── RAGX-0138: editar uma linha reaproveita os chunks e só embute o novo ─
def test_editar_uma_linha_reaproveita_chunks_e_vetores(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx.embeddings.hashing import HashingEmbedder

    cfg = load_config(proj)
    (proj / "src" / "grande.py").write_text(
        "".join(f"def f{i}(x):\n    return x + {i}\n\n\n" for i in range(12)), encoding="utf-8"
    )
    index_project(cfg)

    def contar(rel: str) -> tuple[int, int]:
        conn = sqlite3.connect(cfg.db_path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id=c.document_id "
                             "WHERE d.rel_path=?", (rel,)).fetchone()[0]
            e = conn.execute("SELECT COUNT(*) FROM embeddings e JOIN chunks c ON c.id=e.chunk_id "
                             "JOIN documents d ON d.id=c.document_id WHERE d.rel_path=?", (rel,)).fetchone()[0]
        finally:
            conn.close()
        return n, e

    antes = contar("src/grande.py")
    textos: list[int] = []
    original = HashingEmbedder.embed_documents

    def espia(self, texts):  # type: ignore[no-untyped-def]
        textos.append(len(texts))
        return original(self, texts)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", espia)
    src = (proj / "src" / "grande.py").read_text(encoding="utf-8")
    (proj / "src" / "grande.py").write_text(src.replace("return x + 5", "return x + 500"), encoding="utf-8")
    r = index_project(cfg)

    assert r.chunks_kept >= 1 and r.chunks_removed == 1
    assert contar("src/grande.py") == antes  # nenhum vetor perdido
    assert sum(textos) == 1, f"só o chunk editado devia ir ao embedder: {textos}"


def test_pontes_do_grafo_dos_chunks_intactos_sobrevivem_a_uma_edicao(proj: Path) -> None:
    from ragx.graph.service import rebuild

    cfg = load_config(proj)
    (proj / "src" / "grafo.py").write_text(
        "".join(f"def g{i}(x):\n    return x * {i}\n\n\n" for i in range(10)), encoding="utf-8"
    )
    index_project(cfg)
    rebuild(cfg)

    def pontes() -> tuple[int, int]:
        conn = sqlite3.connect(cfg.db_path)
        try:
            com = conn.execute("SELECT COUNT(*) FROM entities e JOIN documents d ON d.id=e.document_id "
                               "WHERE d.rel_path='src/grafo.py' AND e.chunk_id IS NOT NULL").fetchone()[0]
            sem = conn.execute("SELECT COUNT(*) FROM entities e JOIN documents d ON d.id=e.document_id "
                               "WHERE d.rel_path='src/grafo.py' AND e.chunk_id IS NULL").fetchone()[0]
        finally:
            conn.close()
        return com, sem

    com0, sem0 = pontes()
    assert com0 >= 10  # sem0: entidades sem chunk próprio (ex.: o módulo), o ponto de partida
    src = (proj / "src" / "grafo.py").read_text(encoding="utf-8")
    (proj / "src" / "grafo.py").write_text(src.replace("return x * 4", "return x * 400"), encoding="utf-8")
    index_project(cfg)
    com1, sem1 = pontes()
    # antes: TODAS as pontes do arquivo viravam NULL até o próximo `sync`; agora só a do chunk editado
    assert sem1 <= sem0 + 1 and com1 >= com0 - 1


# --- RAGX-0146: cache de embedding em lote, checkpoint e uma consulta só ---------------------------------------------


class _Contador:
    """Embedder falso: conta quantos textos recebeu e pode morrer no N-ésimo lote."""

    id = "falso:0146"
    dim = 128

    def __init__(self, morre_no_lote: int | None = None) -> None:
        self.textos = 0
        self.lotes = 0
        self.morre_no_lote = morre_no_lote

    def available(self) -> bool:
        return True

    def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        import numpy as np

        self.lotes += 1
        if self.morre_no_lote is not None and self.lotes == self.morre_no_lote:
            raise RuntimeError("morreu no meio")
        self.textos += len(texts)
        return np.ones((len(texts), self.dim), dtype=np.float32)

    def embed_query(self, text):  # type: ignore[no-untyped-def]
        import numpy as np

        return np.ones(self.dim, dtype=np.float32)


def _com_chunks(proj: Path, n: int = 30) -> None:
    for i in range(n):
        (proj / "src" / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")


def _embute(proj: Path, monkeypatch: pytest.MonkeyPatch, emb: _Contador, batch: int = 4):  # type: ignore[no-untyped-def]
    from ragx.indexing import embed as embed_mod

    cfg = load_config(proj)
    cfg.embedding.batch = batch
    monkeypatch.setattr(embed_mod, "build_embedder", lambda _cfg: emb)
    monkeypatch.setattr(embed_mod, "embedder_id", lambda _cfg: emb.id)
    index_project(cfg, embed=False)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    try:
        return embed_mod.embed_pending(cfg, conn), cfg
    finally:
        conn.close()


def test_segunda_rodada_nao_chama_o_embedder_e_nao_cria_arquivo_por_chunk(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _com_chunks(proj)
    emb = _Contador()
    r1, cfg = _embute(proj, monkeypatch, emb)
    assert r1.embedded > 0 and emb.textos == r1.embedded
    antes = emb.textos
    r2, _ = _embute(proj, monkeypatch, emb)
    assert emb.textos == antes and r2.pending == 0
    arquivos = [p for p in (cfg.state_dir / "cache" / "emb").rglob("*") if p.is_file()]
    assert arquivos and all(".sqlite" in p.name for p in arquivos)  # `.sqlite`, `-wal` e `-shm`


def test_processo_morto_no_meio_retoma_do_ultimo_lote_concluido(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _com_chunks(proj)
    morre = _Contador(morre_no_lote=3)
    r1, cfg = _embute(proj, monkeypatch, morre)
    assert r1.error and morre.textos == 8  # 2 lotes de 4 chegaram antes
    conn = sqlite3.connect(cfg.db_path)
    gravados = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    conn.close()
    assert gravados == 8  # o que tinha lote concluído foi gravado mesmo com a falha

    sobra = _Contador()
    r2, _ = _embute(proj, monkeypatch, sobra)
    assert r2.error is None
    assert sobra.textos == r2.pending - r2.from_cache or sobra.textos <= r2.pending
    assert sobra.textos + 8 == r1.pending  # nada do que já estava pronto foi reembutido


def test_consultas_sql_do_embed_nao_crescem_com_o_numero_de_chunks(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragx.indexing import embed as embed_mod

    contagens = []
    for n in (10, 60):
        sub = proj / f"p{n}"
        (sub / "src").mkdir(parents=True)
        (sub / "ragx.toml").write_text((proj / "ragx.toml").read_text(encoding="utf-8"), encoding="utf-8")
        _com_chunks(sub, n)
        cfg = load_config(sub)
        index_project(cfg, embed=False)
        emb = _Contador()
        monkeypatch.setattr(embed_mod, "build_embedder", lambda _cfg, e=emb: e)
        monkeypatch.setattr(embed_mod, "embedder_id", lambda _cfg, e=emb: e.id)
        conn = sqlite3.connect(cfg.db_path)
        conn.row_factory = sqlite3.Row
        vistas: list[str] = []
        conn.set_trace_callback(vistas.append)
        embed_mod.embed_pending(cfg, conn)
        conn.close()
        contagens.append(sum(1 for q in vistas if q.lstrip().upper().startswith("SELECT")))
    assert contagens[1] <= contagens[0] + 2  # 6x mais chunks, quase o mesmo número de SELECTs


@pytest.mark.parametrize("kind,symbol,heading", [("method", "A.m", None), ("section", None, "T > S"), ("file", None, None)])
def test_texto_enviado_ao_embedder_e_o_mesmo_de_antes(kind: str, symbol: str | None, heading: str | None) -> None:
    """Regressão: o prefixo de contexto continua `context_prefix` do `Chunk`, com símbolo, título ou nenhum."""
    from ragx.core.models import Chunk, ChunkKind
    from ragx.indexing.chunkers import context_prefix
    from ragx.indexing.embed import _prefixed

    chunk = Chunk(
        id="c", document_id="", ordinal=0, kind=ChunkKind(kind), start_line=0, end_line=0,
        content="corpo", content_hash="", token_count=0, symbol=symbol, heading_path=heading,
    )
    assert _prefixed("src/a.py", "corpo", "c", kind, symbol, heading) == context_prefix("src/a.py", chunk)
