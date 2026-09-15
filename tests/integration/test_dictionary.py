"""Fase 5 — Knowledge Dictionary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.dictionary import builder
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.tokens import count_tokens

pytestmark = pytest.mark.integration

PYPROJECT = """[project]
name = "demo"
dependencies = ["fastapi", "redis", "pydantic"]
"""

AUTH = '''class AuthService:
    """Autentica usuarios via SSO."""

    def login(self, c):
        """Valida o token."""
        return self.sso.validate(c)
'''

PAY = '''class PaymentService:
    """Cobra o cliente no gateway externo."""

    def charge(self, order):
        """Envia a cobranca."""
        return self.gateway.charge(order)
'''

NOTIFY = '''class NotificationService:
    """Envia notificacoes."""

    def send(self, msg):
        """Publica a mensagem na fila."""
        return self.queue.publish(msg)
'''

ROUTES = """from fastapi import APIRouter

router = APIRouter()


@router.post("/api/login")
def login_route(payload):
    return payload
"""

SCHEMA = "CREATE TABLE users (\n  id INTEGER PRIMARY KEY\n);\n"
DOC = "# SSO e MFA\n\nO AuthService valida o token contra o provedor.\n"


@pytest.fixture(scope="module")
def proj(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dict")
    (root / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\nkind = "http-service"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "src" / "payment.py").write_text(PAY, encoding="utf-8")
    (root / "src" / "notify.py").write_text(NOTIFY, encoding="utf-8")
    (root / "routes.py").write_text(ROUTES, encoding="utf-8")
    (root / "schema.sql").write_text(SCHEMA, encoding="utf-8")
    (root / "doc.md").write_text(DOC, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


def _build(proj: Path) -> dict:
    data, _ = builder.build(load_config(proj))
    return data


# ── critério de aceite ──────────────────────────────────────────────────
def test_gera_sem_nenhum_llm(proj: Path) -> None:
    data = _build(proj)
    assert data["technologies"] and data["services"] and data["modules"]
    assert data["entrypoints"] and data["data_stores"]


def test_tecnologias_vem_de_dependencia_declarada(proj: Path) -> None:
    nomes = {t["name"] for t in _build(proj)["technologies"]}
    assert {"FastAPI", "Redis", "Pydantic"} <= nomes


def test_servicos_detectados_por_convencao(proj: Path) -> None:
    nomes = {s["name"] for s in _build(proj)["services"]}
    assert {"AuthService", "PaymentService", "NotificationService"} <= nomes


def test_todo_item_tem_evidencia(proj: Path) -> None:
    """Item sem evidência não pode ser auditado — e alucinação entra por aí."""
    data = _build(proj)
    for t in data["technologies"]:
        assert t["evidence"], f"tecnologia sem evidência: {t['name']}"
    for c in data["conventions"]:
        assert c["evidence"], f"convenção sem evidência: {c['rule']}"
    for s in data["services"]:
        assert s["path"], f"serviço sem caminho: {s['name']}"


def test_endpoints_e_tabelas(proj: Path) -> None:
    data = _build(proj)
    assert any(e["value"] == "POST /api/login" for e in data["entrypoints"])
    assert any(d["name"] == "users" for d in data["data_stores"])


def test_cabe_no_orcamento_de_tokens(proj: Path) -> None:
    """Um mapa que custa mais que a pergunta que evita não serve para nada."""
    data = _build(proj)
    assert count_tokens(json.dumps(data, ensure_ascii=False)) <= 8000


def test_regeneracao_e_identica(proj: Path) -> None:
    """Sem isso, `git diff knowledge/` nunca estabiliza."""
    a = builder.stable_digest(_build(proj))
    b = builder.stable_digest(_build(proj))
    assert a == b


def test_generated_at_fica_fora_do_digest(proj: Path) -> None:
    d1 = _build(proj)
    d2 = _build(proj)
    d2["project"]["generated_at"] = "2030-01-01T00:00:00Z"
    assert builder.stable_digest(d1) == builder.stable_digest(d2)


def test_escrita_e_estavel_e_ordenada(proj: Path) -> None:
    cfg = load_config(proj)
    data = _build(proj)
    builder.write(cfg, data)
    body = (proj / "knowledge" / "dictionary.json").read_text(encoding="utf-8")
    assert "\r\n" not in body, "CRLF quebraria o diff entre plataformas"
    reparsed = json.loads(body)
    assert list(reparsed) == sorted(reparsed), "chaves precisam estar ordenadas"


def test_load_devolve_o_que_foi_escrito(proj: Path) -> None:
    cfg = load_config(proj)
    data = _build(proj)
    builder.write(cfg, data)
    assert builder.load(cfg) == data


def test_load_sem_arquivo_devolve_none(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert builder.load(load_config(tmp_path)) is None


def test_stats_refletem_o_indice(proj: Path) -> None:
    stats = _build(proj)["stats"]
    assert stats["documents"] > 0 and stats["chunks"] > 0 and stats["entities"] > 0


def test_convencoes_exigem_repeticao(proj: Path) -> None:
    for c in _build(proj)["conventions"]:
        assert c["occurrences"] >= 3, "convenção com menos de 3 ocorrências é ruído"
