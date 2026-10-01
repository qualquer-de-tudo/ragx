from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.context.engine import build_context
from ragx.context.render import explain, render
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios contra o provedor SSO corporativo."""

    def login(self, credentials):
        """Valida o token e cria a sessao no Redis com TTL de 30 minutos."""
        session = self.sso.validate(credentials)
        self.redis.setex(session.id, 1800, session.payload)
        return session
'''

DOC = """# Autenticacao

## Fluxo SSO

O sistema delega a verificacao de identidade ao provedor corporativo.
Depois de validado o usuario recebe uma sessao guardada no Redis.

## Expiracao

A sessao expira automaticamente apos 30 minutos. Nao existe renovacao silenciosa.
"""

LONGO = "# Manual\n\n## Detalhes\n\n" + "\n\n".join(
    f"Paragrafo {i} com bastante texto para gastar bastante espaco de contexto "
    f"e obrigar o motor a comprimir ou descartar alguma coisa." for i in range(120)
)

DUPLICADO = """# Copia

## Fluxo SSO

O sistema delega a verificacao de identidade ao provedor corporativo.
Depois de validado o usuario recebe uma sessao guardada no Redis.
"""


@pytest.fixture(scope="module")
def proj(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ctx")
    (root / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "doc.md").write_text(DOC, encoding="utf-8")
    (root / "copia.md").write_text(DUPLICADO, encoding="utf-8")
    (root / "manual.md").write_text(LONGO, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


# ── Critério de aceite central da Fase 4 ────────────────────────────────
@pytest.mark.parametrize("budget", [500, 1000, 3000])
def test_sempre_cabe_no_orcamento(proj: Path, budget: int) -> None:
    pack = build_context(load_config(proj), "autenticacao sessao", budget=budget, use_cache=False)
    assert pack.estimated_tokens <= budget, f"{pack.estimated_tokens} > {budget}"


def test_recuperacao_grande_vira_pack_pequeno(proj: Path) -> None:
    """10k tokens recuperados -> pack dentro do teto, sem perder as fontes."""
    pack = build_context(load_config(proj), "autenticacao", budget=800, use_cache=False)
    assert pack.stats["raw_tokens"] > pack.estimated_tokens * 2
    assert pack.estimated_tokens <= 800
    assert pack.fragments


# ── Fonte preservada ────────────────────────────────────────────────────
def test_todo_fragmento_tem_fonte_e_linhas(proj: Path) -> None:
    pack = build_context(load_config(proj), "sessao redis", budget=2000, use_cache=False)
    assert pack.fragments
    for f in pack.fragments:
        assert f.document_path
        assert f.start_line > 0 and f.end_line >= f.start_line
        assert f.project == "current"


def test_compressao_so_quando_realmente_precisa(proj: Path) -> None:
    """`allocate` já escolhe um conjunto que cabe; comprimir por padrão depois
    disso desperdiça orçamento."""
    pack = build_context(load_config(proj), "autenticacao", budget=4000, use_cache=False)
    assert pack.fragments
    assert pack.stats["compressed"] == 0, (
        "com orçamento folgado nada deveria ser comprimido — "
        "comprimir por padrão devolve ao agente menos contexto do que caberia"
    )
    assert all(not f.compressed for f in pack.fragments)


def test_chunk_maior_que_o_orcamento_ainda_devolve_contexto(proj: Path) -> None:
    """Devolver vazio seria pior que devolver o trecho comprimido — o agente
    perderia a única fonte relevante."""
    pack = build_context(load_config(proj), "manual detalhes paragrafo",
                         budget=250, use_cache=False)
    assert pack.fragments, "pack vazio: a única fonte relevante foi descartada"
    assert pack.estimated_tokens <= 250
    for f in pack.fragments:
        assert f.document_path and f.start_line > 0


# ── Dedup ───────────────────────────────────────────────────────────────
def test_sem_duplicata_literal_no_pack(proj: Path) -> None:
    pack = build_context(load_config(proj), "fluxo SSO provedor", budget=3000, use_cache=False)
    corpos = [f.content for f in pack.fragments]
    assert len(corpos) == len(set(corpos))


def test_duplicata_e_registrada_como_descarte(proj: Path) -> None:
    pack = build_context(load_config(proj), "fluxo SSO provedor", budget=3000, use_cache=False)
    assert any("duplicate_of" in why for _cid, why in pack.dropped)


# ── Diversidade de fontes ───────────────────────────────────────────────
def test_pelo_menos_duas_fontes_quando_existem(proj: Path) -> None:
    pack = build_context(load_config(proj), "autenticacao sessao redis", budget=2500, use_cache=False)
    assert len(pack.sources) >= 2, f"colapsou em {pack.sources}"


# ── Intenção ────────────────────────────────────────────────────────────
def test_intencao_e_registrada(proj: Path) -> None:
    assert build_context(
        load_config(proj), "implementar login", budget=800, use_cache=False
    ).intent == "implement"


# ── Cache ───────────────────────────────────────────────────────────────
def test_cache_acelera_e_marca(proj: Path) -> None:
    cfg = load_config(proj)
    a = build_context(cfg, "cache teste unico", budget=900)
    b = build_context(cfg, "cache teste unico", budget=900)
    assert not a.cached and b.cached
    assert [f.content for f in a.fragments] == [f.content for f in b.fragments]


def test_cache_invalida_apos_reindexar(proj: Path, tmp_path: Path) -> None:
    cfg = load_config(proj)
    build_context(cfg, "invalidacao de cache", budget=900)
    (proj / "novo.md").write_text("# Novo\n\nConteudo novo sobre sessao.\n", encoding="utf-8")
    index_project(cfg)
    assert not build_context(cfg, "invalidacao de cache", budget=900).cached


def test_no_cache_ignora_o_cache(proj: Path) -> None:
    cfg = load_config(proj)
    build_context(cfg, "sem cache", budget=900)
    assert not build_context(cfg, "sem cache", budget=900, use_cache=False).cached


# ── Sem grafo ───────────────────────────────────────────────────────────
def test_funciona_sem_grafo(proj: Path) -> None:
    """O Context Engine não pode depender da Fase 3."""
    pack = build_context(
        load_config(proj), "autenticacao", budget=1000, include_graph=False, use_cache=False
    )
    assert pack.fragments


# ── Formatação ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("fmt", ["markdown", "json", "xml"])
def test_formatos(proj: Path, fmt: str) -> None:
    pack = build_context(load_config(proj), "sessao", budget=1000, use_cache=False)
    body = render(pack, fmt)
    assert body and pack.fragments[0].document_path in body


def test_markdown_traz_fonte_e_rodape(proj: Path) -> None:
    pack = build_context(load_config(proj), "sessao", budget=1000, use_cache=False)
    md = render(pack, "markdown")
    assert md.startswith("# Contexto —")
    assert "tokens" in md.splitlines()[-1]


def test_explain_justifica_tudo(proj: Path) -> None:
    pack = build_context(load_config(proj), "autenticacao", budget=700, use_cache=False)
    texto = explain(pack)
    assert "Intenção detectada" in texto and "INCLUÍDOS" in texto
    for f in pack.fragments:
        assert f.document_path in texto
    if pack.dropped:
        assert "DESCARTADOS" in texto


def test_consulta_sem_resultado_devolve_pack_vazio(proj: Path) -> None:
    pack = build_context(
        load_config(proj), "zzz", budget=500, include_graph=False, use_cache=False
    )
    assert pack.estimated_tokens <= 500


def test_e_rapido(proj: Path) -> None:
    pack = build_context(load_config(proj), "autenticacao sessao", budget=3000, use_cache=False)
    assert pack.stats["total_ms"] < 1500


# ── RAGX-0135: o cache só devolve o que a chamada pediu ─────────────────
def test_cache_nao_mistura_filtros(proj: Path) -> None:
    """Demonstrado na auditoria: `lang=markdown` e depois `lang=python`, mesma
    consulta, devolviam `cached=True` e o MESMO pack."""
    from ragx.search.service import SearchFilters

    cfg = load_config(proj)
    md = build_context(cfg, "sessao redis autenticacao", budget=900,
                       filters=SearchFilters(lang="markdown"))
    py = build_context(cfg, "sessao redis autenticacao", budget=900,
                       filters=SearchFilters(lang="python"))
    assert not py.cached
    assert {f.document_path for f in md.fragments} != {f.document_path for f in py.fragments}
    assert all(f.document_path.endswith(".md") for f in md.fragments)
    assert all(f.document_path.endswith(".py") for f in py.fragments)
    # e cada um, repetido, acerta o SEU cache
    assert build_context(cfg, "sessao redis autenticacao", budget=900,
                         filters=SearchFilters(lang="python")).cached


def test_o_que_altera_o_resultado_altera_a_chave(proj: Path) -> None:
    from ragx.context.engine import _cache_key
    from ragx.search.service import SearchFilters

    cfg = load_config(proj)
    base = _cache_key(cfg, "q", 900, True, None, None)
    assert base == _cache_key(cfg, "q", 900, True, None, None)
    assert base != _cache_key(cfg, "q", 901, True, None, None)
    assert base != _cache_key(cfg, "q", 900, False, None, None)
    assert base != _cache_key(cfg, "q", 900, True, 2, None)
    assert base != _cache_key(cfg, "q", 900, True, None, SearchFilters(lang="python"))
    assert base != _cache_key(cfg, "q", 900, True, None, SearchFilters(path_glob="*.md"))
    assert base != _cache_key(cfg, "q", 900, True, None, SearchFilters(min_score=0.2))
    for campo, valor in (
        ("context", {"dedup_threshold": 0.5}),
        ("context", {"reserve_ratio": 0.2}),
        ("context", {"min_sources": 1}),
        ("search", {"weight_keyword": 0.1}),
        ("search", {"rrf_k": 5}),
        ("graph", {"max_nodes": 3}),
        ("index", {"work_paths": ["task/"]}),
    ):
        outro = load_config(proj)
        for k, v in valor.items():
            setattr(getattr(outro, campo), k, v)
        assert base != _cache_key(outro, "q", 900, True, None, None), (campo, valor)


def test_propriedade_cache_nunca_devolve_pack_diferente_do_calculado(proj: Path) -> None:
    """S12: 200 combinações pseudoaleatórias; sempre que há acerto de cache, o pack
    é idêntico ao calculado do zero."""
    import random

    from ragx.search.service import SearchFilters

    rng = random.Random(1234)
    consultas = ["autenticacao sessao", "redis ttl", "fluxo sso", "manual detalhes", "expiracao"]
    filtros = [None, SearchFilters(lang="markdown"), SearchFilters(lang="python"),
               SearchFilters(path_glob="*.md"), SearchFilters(kind="code")]
    acertos = 0
    for _ in range(200):
        cfg = load_config(proj)
        cfg.context.mmr_lambda = rng.choice([0.3, 0.7, 0.9])
        cfg.context.dedup_threshold = rng.choice([0.8, 0.93])
        cfg.search.weight_keyword = rng.choice([0.4, 0.8])
        args = {
            "query": rng.choice(consultas),
            "budget": rng.choice([400, 900, 3000]),
            "include_graph": rng.choice([True, False]),
            "depth": rng.choice([None, 1, 2]),
            "filters": rng.choice(filtros),
        }
        a = build_context(cfg, **args)
        if a.cached:
            acertos += 1
        b = build_context(cfg, **args, use_cache=False)
        assert [(f.document_path, f.start_line, f.content) for f in a.fragments] == [
            (f.document_path, f.start_line, f.content) for f in b.fragments
        ], args
        assert a.estimated_tokens == b.estimated_tokens, args
    assert acertos > 0  # o cache existe e foi exercitado


def test_run_aberta_nao_grava_no_cache_e_depois_grava(tmp_path: Path) -> None:
    from ragx.context.engine import _cache_dir
    from ragx.indexing import lock
    from ragx.storage.db import open_db
    from ragx.storage.repositories import RunRepo

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)

    def arquivos() -> int:
        d = _cache_dir(cfg)
        return len(list(d.glob("*.json"))) if d.exists() else 0

    assert lock.try_acquire(cfg.state_dir, "index", "test")
    with open_db(cfg.db_path) as conn:
        run_id = RunRepo(conn).start("incremental", "test", None)  # run ABERTA, sem finish
        conn.commit()
    try:
        build_context(cfg, "sessao redis", budget=500)
        assert arquivos() == 0, "pack de run em andamento não pode entrar no cache"
    finally:
        with open_db(cfg.db_path) as conn:
            RunRepo(conn).finish(run_id, {})
            conn.commit()
        lock.release(cfg.state_dir)
    build_context(cfg, "sessao redis", budget=500)
    assert arquivos() == 1


# ── RAGX-0154: `estimated_tokens` conta o que SAI ───────────────────────
@pytest.mark.parametrize("budget", [500, 1000, 3000])
def test_estimated_tokens_conta_o_que_sai(proj: Path, budget: int) -> None:
    """Antes: `estimated_tokens` somava só o `content` dos fragmentos e ignorava os
    cabeçalhos (~33 tokens cada, contra os 12 que `allocate` assumia) e o rodapé."""
    from ragx.tokens import count_tokens

    pack = build_context(load_config(proj), "autenticacao sessao redis", budget=budget,
                         use_cache=False)
    assert pack.fragments
    saiu = count_tokens(render(pack, "markdown", title=False))
    assert saiu <= budget, f"saiu {saiu} > orçamento {budget}"
    assert pack.estimated_tokens == saiu, (pack.estimated_tokens, saiu)
    assert pack.stats["content_tokens"] + pack.stats["overhead_tokens"] == pack.estimated_tokens


def test_render_sem_titulo_nao_imprime_a_consulta(proj: Path) -> None:
    pack = build_context(load_config(proj), "consulta muito especifica xyz", budget=900,
                         use_cache=False)
    assert "# Contexto" in render(pack, "markdown")
    assert "# Contexto" not in render(pack, "markdown", title=False)
    assert "xyz" not in render(pack, "markdown", title=False)


def test_fragmento_carrega_o_chunk_id(proj: Path) -> None:
    pack = build_context(load_config(proj), "autenticacao sessao", budget=900, use_cache=False)
    assert pack.fragments and all(len(f.chunk_id) == 32 for f in pack.fragments)
    assert '"chunk_id"' in render(pack, "json")
