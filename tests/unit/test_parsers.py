from __future__ import annotations

import pytest

from ragx.core.models import ChunkKind, DocKind
from ragx.indexing import parsers

pytestmark = pytest.mark.unit

PY = '''"""Módulo de auth."""
import os
from typing import Any

MAX = 3


class AuthService:
    """Autentica usuários."""

    @property
    def ready(self) -> bool:
        return True

    async def login(self, user: str) -> Any:
        """Faz login."""
        return os.environ.get(user)


def helper() -> int:
    return MAX
'''

MD = """# Título

Intro.

## Arquitetura

Texto da arquitetura.

### Autenticação

Detalhe.

```python
# isto NÃO é um heading
def x(): pass
```

| a | b |
|---|---|
| 1 | 2 |
"""


def test_python_extrai_hierarquia() -> None:
    r = parsers.parse("a.py", PY)
    assert r is not None and r.lang == "python" and r.doc_kind is DocKind.CODE
    cls = next(n for n in r.nodes if n.kind is ChunkKind.CLASS)
    assert cls.symbol == "AuthService"
    metodos = {c.symbol for c in cls.children}
    assert metodos == {"AuthService.ready", "AuthService.login"}


def test_python_preambulo_captura_imports() -> None:
    r = parsers.parse("a.py", PY)
    pre = next(n for n in r.nodes if n.kind is ChunkKind.FILE)
    assert "os" in pre.meta["imports"] and "typing.Any" in pre.meta["imports"]


def test_python_decorator_entra_no_intervalo() -> None:
    r = parsers.parse("a.py", PY)
    cls = next(n for n in r.nodes if n.kind is ChunkKind.CLASS)
    ready = next(c for c in cls.children if c.symbol.endswith("ready"))
    assert PY.splitlines()[ready.start_line - 1].strip() == "@property"


def test_python_async_e_reconhecido() -> None:
    r = parsers.parse("a.py", PY)
    cls = next(n for n in r.nodes if n.kind is ChunkKind.CLASS)
    login = next(c for c in cls.children if c.symbol.endswith("login"))
    assert login.meta["is_async"]


def test_python_erro_de_sintaxe_degrada_sem_excecao() -> None:
    r = parsers.parse("bad.py", "def (:\n  ???\n")
    assert r is not None and r.degraded


def test_markdown_heading_path() -> None:
    r = parsers.parse("d.md", MD)
    paths = [n.meta.get("heading_path") for n in r.nodes]
    assert "Título > Arquitetura > Autenticação" in paths


def test_markdown_ignora_hash_dentro_de_bloco_de_codigo() -> None:
    r = parsers.parse("d.md", MD)
    simbolos = [n.symbol for n in r.nodes]
    assert "isto NÃO é um heading" not in simbolos


def test_markdown_protege_bloco_e_tabela() -> None:
    r = parsers.parse("d.md", MD)
    auth = next(n for n in r.nodes if n.symbol == "Autenticação")
    assert len(auth.meta["protected"]) >= 2, "fence e tabela precisam ser protegidos"


def test_markdown_titulo() -> None:
    assert parsers.parse("d.md", MD).title == "Título"


def test_sql_create_table_vira_simbolo() -> None:
    r = parsers.parse("s.sql", "CREATE TABLE users (\n id INT\n);\n\nSELECT 1;\n")
    assert any(n.symbol == "users" for n in r.nodes)


def test_json_corta_por_chave_de_topo() -> None:
    r = parsers.parse("p.json", '{\n "name": "x",\n "deps": {\n  "a": "1"\n }\n}\n')
    assert {n.symbol for n in r.nodes} == {"$.name", "$.deps"}


def test_yaml_corta_por_chave_de_topo() -> None:
    r = parsers.parse("c.yml", "services:\n  db:\n    image: x\nvolumes:\n  a: b\n")
    assert {n.symbol for n in r.nodes} == {"services", "volumes"}


def test_extensao_desconhecida_e_ignorada_por_padrao() -> None:
    assert parsers.parse("x.rb", "puts 1") is None
    assert parsers.parse("x.rb", "puts 1", include_unknown=True) is not None
