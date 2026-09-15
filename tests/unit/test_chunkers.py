from __future__ import annotations

import pytest

from ragx.core.models import ChunkKind
from ragx.indexing import parsers
from ragx.indexing.chunkers import ChunkOptions, chunk_document, context_prefix

pytestmark = pytest.mark.unit

PY = '''import os


class AuthService:
    """Autentica."""

    def login(self, user):
        """Login."""
        token = os.environ.get(user)
        return token

    def logout(self):
        return True


def helper():
    return 1
'''


def _chunks(path: str, text: str, **kw):
    parsed = parsers.parse(path, text, include_unknown=True)
    return chunk_document(path, text, parsed, ChunkOptions(**kw))


def test_metodo_nao_e_cortado_ao_meio() -> None:
    cs = _chunks("a.py", PY)
    login = next(c for c in cs if c.symbol == "AuthService.login")
    assert "def login" in login.content and "return token" in login.content


def test_classe_nao_repete_o_corpo_dos_metodos() -> None:
    cs = _chunks("a.py", PY)
    cls = next(c for c in cs if c.kind is ChunkKind.CLASS)
    assert "return token" not in cls.content
    assert "métodos: login, logout" in cls.content


def test_parent_id_liga_metodo_a_classe() -> None:
    cs = _chunks("a.py", PY)
    cls = next(c for c in cs if c.kind is ChunkKind.CLASS)
    metodos = [c for c in cs if c.symbol and c.symbol.startswith("AuthService.")]
    assert metodos and all(m.parent_id == cls.id for m in metodos)


def test_unidade_grande_divide_em_partes_nomeadas() -> None:
    corpo = "\n".join(f"    x{i} = {i} + {i} * {i}" for i in range(400))
    cs = _chunks("big.py", f"def grande():\n{corpo}\n", max_tokens=100)
    partes = [c for c in cs if c.symbol and "#part-" in c.symbol]
    assert len(partes) > 1
    assert all(c.token_count <= 400 for c in partes)


def test_fatiamento_e_deterministico() -> None:
    a = [c.id for c in _chunks("a.py", PY)]
    b = [c.id for c in _chunks("a.py", PY)]
    assert a == b


def test_ordinal_e_contiguo() -> None:
    cs = _chunks("a.py", PY)
    assert [c.ordinal for c in cs] == list(range(len(cs)))


def test_token_count_preenchido() -> None:
    assert all(c.token_count > 0 for c in _chunks("a.py", PY))


def test_bloco_de_codigo_markdown_nao_e_partido() -> None:
    bloco = "\n".join(f"linha {i} de codigo com algum texto" for i in range(120))
    md = f"# T\n\n## S\n\nintro\n\n```python\n{bloco}\n```\n\nfim\n"
    cs = _chunks("d.md", md, max_tokens=50)
    fences = sum(c.content.count("```") for c in cs)
    assert fences == 2, "o fence foi partido entre chunks"


def test_heading_path_preservado_ao_dividir() -> None:
    longo = "\n\n".join(f"Paragrafo {i} com bastante texto para gastar tokens." for i in range(80))
    md = f"# T\n\n## Arquitetura\n\n{longo}\n"
    cs = _chunks("d.md", md, max_tokens=60)
    secoes = [c for c in cs if c.heading_path and "Arquitetura" in c.heading_path]
    assert len(secoes) > 1
    assert all(c.heading_path == "T > Arquitetura" for c in secoes)


def test_chunks_minusculos_sao_fundidos() -> None:
    triviais = "\n\n".join(
        f"class C{i}:\n    def get_x(self):\n        return {i}" for i in range(6)
    )
    cs = _chunks("t.py", triviais + "\n", min_tokens=40)
    assert len(cs) < 18


def test_prefixo_de_contexto_nao_polui_o_conteudo() -> None:
    cs = _chunks("src/a.py", PY)
    c = next(x for x in cs if x.symbol == "AuthService.login")
    assert "src/a.py" not in c.content
    assert "src/a.py" in context_prefix("src/a.py", c)


def test_conteudo_identico_no_mesmo_documento_nao_colide() -> None:
    """Regressão: dois helpers byte-idênticos geravam o mesmo chunk_id e
    estouravam a PK. Encontrado indexando o próprio RAGX."""
    src = "def a():\n    return 1\n\n\ndef b():\n    return 1\n"
    # mesmo corpo, assinaturas distintas -> ok; agora o caso realmente idêntico:
    dup = "# nota\n\n\n# nota\n"
    for texto, path in ((src, "x.py"), (dup, "y.md")):
        cs = _chunks(path, texto)
        ids = [c.id for c in cs]
        assert len(ids) == len(set(ids)), f"ids duplicados em {path}: {ids}"


def test_dedupe_preserva_intervalos_de_linha() -> None:
    md = "# T\n\n## A\n\ntexto igual\n\n## B\n\ntexto igual\n"
    cs = _chunks("d.md", md)
    iguais = [c for c in cs if c.content.strip().endswith("texto igual")]
    assert len({c.id for c in iguais}) == len(iguais)
    assert len({c.start_line for c in iguais}) == len(iguais), "linhas foram perdidas"


def test_chunk_fundido_tem_id_coerente_com_o_conteudo() -> None:
    """Regressão: _merge_tiny mantinha o id antigo após mudar o conteúdo."""
    from ragx.core.ids import CHUNKER_VERSION, chunk_id

    triviais = "\n\n".join(f"def g{i}():\n    return {i}" for i in range(8))
    cs = _chunks("t.py", triviais + "\n", min_tokens=40)
    for c in cs:
        assert c.id == chunk_id("t.py", c.content, CHUNKER_VERSION) or "::ragx-dup-" in str(c.id)
