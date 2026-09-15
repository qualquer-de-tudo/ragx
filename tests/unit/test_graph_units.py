from __future__ import annotations

import pytest

from ragx.core.ids import entity_id, relation_id
from ragx.graph.extractors.reference import _declared_deps, _imports, _normalize_route
from ragx.graph.store import Entity, EntityType, Relation, RelationType

pytestmark = pytest.mark.unit


def test_entity_id_e_deterministico() -> None:
    a = Entity(EntityType.CLASS, "AuthService", "src/a.py::AuthService")
    b = Entity(EntityType.CLASS, "AuthService", "src/a.py::AuthService")
    assert a.id == b.id == entity_id("class", "src/a.py::AuthService")


def test_entity_id_distingue_tipo_e_arquivo() -> None:
    mesma_classe_outro_arquivo = Entity(EntityType.CLASS, "A", "src/b.py::A")
    assert Entity(EntityType.CLASS, "A", "src/a.py::A").id != mesma_classe_outro_arquivo.id
    assert Entity(EntityType.CLASS, "A", "x").id != Entity(EntityType.FUNCTION, "A", "x").id


def test_relation_id_e_deterministico_e_direcional() -> None:
    assert Relation("a", "b", RelationType.CALLS).id == relation_id("a", "calls", "b")
    assert Relation("a", "b", RelationType.CALLS).id != Relation("b", "a", RelationType.CALLS).id


@pytest.mark.parametrize(
    "rota,esperado",
    [
        ("/api/orders/{id}", "/api/orders/{}"),          # Laravel / OpenAPI
        ("/api/orders/:id", "/api/orders/{}"),           # Express
        ("/api/orders/<int:id>", "/api/orders/{}"),      # Flask
        ("/api/orders/%s", "/api/orders/{}"),            # formatação
        ("api/orders", "/api/orders"),                   # barra inicial
        ("/api//orders/", "/api/orders/"),               # barras duplicadas
    ],
)
def test_normalizacao_de_rota_entre_stacks(rota: str, esperado: str) -> None:
    """Rotas equivalentes precisam virar a MESMA forma — é o que permitirá
    cruzar consumes/provides na Fase 11."""
    assert _normalize_route(rota) == esperado


def test_rotas_equivalentes_convergem() -> None:
    formas = ["/api/users/{id}/posts/{pid}", "/api/users/:id/posts/:pid",
              "/api/users/<int:id>/posts/<pid>"]
    assert len({_normalize_route(f) for f in formas}) == 1


def test_deps_de_package_json() -> None:
    conteudo = '{"dependencies": {"express": "^4"}, "devDependencies": {"vitest": "^1"}}'
    assert set(_declared_deps("package.json", conteudo)) == {"express", "vitest"}


def test_deps_de_pyproject() -> None:
    conteudo = '[project]\ndependencies = ["typer>=0.12", "numpy"]\n'
    assert set(_declared_deps("pyproject.toml", conteudo)) == {"typer", "numpy"}


def test_manifesto_invalido_nao_quebra() -> None:
    assert _declared_deps("package.json", "{ isso nao e json") == []


def test_imports_python() -> None:
    src = "import os\nfrom typing import Any\nimport numpy as np\n"
    out = _imports(src, "python")
    assert "os" in out and "typing" in out


def test_imports_js_e_php() -> None:
    assert "express" in _imports("import x from 'express'", "javascript")
    assert r"App\Auth\Service" in _imports(r"use App\Auth\Service;", "php")
