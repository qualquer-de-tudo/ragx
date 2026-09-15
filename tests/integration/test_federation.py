"""Fase 11 — multiprojeto e federação."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import UsageError
from ragx.federation import hub as hub_mod
from ragx.federation import linker
from ragx.federation import slice as fed_slice
from ragx.federation.search import search_scoped
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration

_TOML = (
    '[project]\nname = "{name}"\nid = "{pid}"\nkind = "http-service"\n'
    'visibility = "{vis}"\n\n'
    '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n'
)

PAYMENT_ROUTES = '''from fastapi import APIRouter

router = APIRouter()


@router.post("/api/payments")
def create_payment(payload):
    """Cria uma cobranca no gateway externo."""
    return payload


@router.post("/api/payments/{payment_id}/refund")
def refund(payment_id):
    """Estorna uma cobranca."""
    return payment_id
'''

PAYMENT_SERVICE = '''class PaymentService:
    """Cobra o cliente e publica o resultado."""

    def charge(self, order):
        """Envia a cobranca e emite payment.captured."""
        self.bus.publish("payment.captured", order)
        return order
'''

ORDER = '''import requests


class OrderService:
    """Orquestra a criacao de pedidos."""

    def checkout(self, order):
        """Cobra o pedido."""
        return requests.post("/api/payments", json=order)

    def cancel(self, order_id):
        """Verbo divergente de proposito."""
        return requests.put(f"/api/payments/{order_id}/refund")

    def ship(self, order):
        """Consome um servico que ninguem registra."""
        return requests.post("/api/tracking/register", json=order)


class Listener:
    def handle(self):
        self.bus.subscribe("payment.captured", self.on_captured)
'''

SHIPPING = '''from fastapi import APIRouter

router = APIRouter()


@router.post("/api/shipping/quote")
def quote(payload):
    """Calcula o frete."""
    return payload
'''


def _make(root: Path, name: str, files: dict[str, str], vis: str = "workspace") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ragx.toml").write_text(
        _TOML.format(name=name, pid=name[:6], vis=vis), encoding="utf-8"
    )
    for fname, body in files.items():
        (root / fname).write_text(body, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    fed_slice.build(cfg)
    return root


@pytest.fixture
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setenv("RAGX_HUB_PATH", str(tmp_path / "hub"))
    pay = _make(tmp_path / "payment-service", "payment-service",
                {"routes.py": PAYMENT_ROUTES, "service.py": PAYMENT_SERVICE})
    ship = _make(tmp_path / "shipping", "shipping", {"routes.py": SHIPPING})
    order = _make(tmp_path / "order-service", "order-service", {"order.py": ORDER})
    return {"pay": pay, "ship": ship, "order": order, "root": tmp_path}


@pytest.fixture
def hub(ws: dict[str, Path]) -> dict[str, Path]:
    cfg = load_config(ws["order"])
    fed = ws["root"] / "shipping.fed.json"
    fed_slice.export_file(load_config(ws["ship"]), fed)
    hub_mod.register(cfg, ws["order"])
    hub_mod.register(cfg, ws["pay"])
    hub_mod.register(cfg, from_federation=fed)
    hub_mod.sync(cfg)
    return ws


# ── fatia ───────────────────────────────────────────────────────────────
def test_fatia_tem_provides_e_consumes(ws: dict[str, Path]) -> None:
    pay = fed_slice.load(ws["pay"] / "knowledge" / "federation")
    order = fed_slice.load(ws["order"] / "knowledge" / "federation")
    rotas = {e["normalized"] for e in pay["provides"]["http"]}
    assert "POST /api/payments" in rotas
    consumidas = {e["normalized"] for e in order["consumes"]["http"]}
    assert "POST /api/payments" in consumidas


def test_eventos_publicados_e_assinados(ws: dict[str, Path]) -> None:
    pay = fed_slice.load(ws["pay"] / "knowledge" / "federation")
    order = fed_slice.load(ws["order"] / "knowledge" / "federation")
    assert any(e["normalized"] == "payment.captured" for e in pay["provides"]["event"])
    assert any(e["normalized"] == "payment.captured" for e in order["consumes"]["event"])


def test_fatia_e_pequena(ws: dict[str, Path]) -> None:
    """Ela contém a superfície, não a implementação."""
    folder = ws["pay"] / "knowledge" / "federation"
    total = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    assert total < 1_048_576


def test_fatia_e_estavel(ws: dict[str, Path]) -> None:
    cfg = load_config(ws["pay"])
    antes = (ws["pay"] / "knowledge" / "federation" / "provides.json").read_bytes()
    fed_slice.build(cfg)
    assert (ws["pay"] / "knowledge" / "federation" / "provides.json").read_bytes() == antes


def test_projeto_privado_nao_gera_fatia(tmp_path: Path) -> None:
    root = _make(tmp_path / "secreto", "secreto", {"routes.py": SHIPPING}, vis="private")
    assert not (root / "knowledge" / "federation").is_dir()


def test_fatia_avulsa_e_autossuficiente(ws: dict[str, Path], tmp_path: Path) -> None:
    """Funciona sem o repositório de origem."""
    alvo = tmp_path / "ship.fed.json"
    fed_slice.export_file(load_config(ws["ship"]), alvo)
    data = fed_slice.load(alvo)
    assert data["service"]["name"] == "shipping"
    assert any(e["normalized"] == "POST /api/shipping/quote" for e in data["provides"]["http"])


# ── registro e hub ──────────────────────────────────────────────────────
def test_registra_clonado_e_so_federacao(hub: dict[str, Path]) -> None:
    rows = {p["name"]: p for p in hub_mod.list_projects(load_config(hub["order"]))}
    assert rows["payment-service"]["cloned"] == 1
    assert rows["shipping"]["cloned"] == 0 and rows["shipping"]["path"] is None


def test_projeto_privado_nao_entra_no_hub(ws: dict[str, Path], tmp_path: Path) -> None:
    root = _make(tmp_path / "priv", "priv", {"routes.py": SHIPPING}, vis="private")
    with pytest.raises(UsageError, match="private"):
        hub_mod.register(load_config(ws["order"]), root)


def test_caminho_sumido_vira_missing_nao_removido(hub: dict[str, Path]) -> None:
    import shutil

    cfg = load_config(hub["order"])
    shutil.rmtree(hub["pay"])
    hub_mod.sync(cfg)
    rows = {p["name"]: p for p in hub_mod.list_projects(cfg)}
    assert "payment-service" in rows, "o projeto não pode sumir do registro"
    assert rows["payment-service"]["status"] == "missing"


def test_hub_sync_e_incremental(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    r = hub_mod.sync(cfg)
    assert all(why == "sem mudanças" for why in r.skipped.values())


def test_hub_reconstroi_apos_reset(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    antes = hub_mod.status(cfg)["items"]
    hub_mod.reset(cfg)
    hub_mod.register(cfg, hub["order"])
    hub_mod.register(cfg, hub["pay"])
    hub_mod.sync(cfg)
    assert hub_mod.status(cfg)["items"] > 0
    assert antes > 0


def test_unregister(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    assert hub_mod.unregister(cfg, "shipping")
    assert "shipping" not in {p["name"] for p in hub_mod.list_projects(cfg)}


# ── vínculos ────────────────────────────────────────────────────────────
def test_resolve_vinculo_http(hub: dict[str, Path]) -> None:
    r = linker.link(load_config(hub["order"]))
    pares = {(lk.src_project, lk.dst_project, lk.normalized) for lk in r.links}
    assert ("order-service", "payment-service", "POST /api/payments") in pares


def test_resolve_vinculo_com_projeto_nao_clonado(hub: dict[str, Path]) -> None:
    """O caso que justifica a fatia existir."""
    cfg = load_config(hub["order"])
    # order consome /api/shipping/quote? não neste fixture — então valida o
    # contrato vindo de um projeto sem repositório local.
    found = linker.find_contract(cfg, "http", "POST /api/shipping/quote")
    assert found and found["project"] == "shipping"


def test_resolve_evento(hub: dict[str, Path]) -> None:
    r = linker.link(load_config(hub["order"]))
    assert any(lk.normalized == "payment.captured" and lk.relation == "subscribes"
               for lk in r.links)


def test_divergencia_de_metodo_e_reportada(hub: dict[str, Path]) -> None:
    """A federação acha erro que nenhum dos dois repositórios vê sozinho."""
    r = linker.link(load_config(hub["order"]))
    assert r.divergences, "PUT vs POST em /api/payments/{}/refund devia divergir"
    d = r.divergences[0]
    assert "método divergente" in d["issue"]


def test_consumo_sem_provedor_e_reportado(hub: dict[str, Path]) -> None:
    r = linker.link(load_config(hub["order"]))
    alvos = {u["target"] for u in r.unresolved}
    assert any("tracking" in t for t in alvos), f"esperava /api/tracking: {alvos}"


def test_link_e_idempotente(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    a = len(linker.link(cfg).links)
    b = len(linker.link(cfg).links)
    assert a == b


def test_dicionario_de_workspace(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    linker.link(cfg)
    d = linker.workspace_dictionary(cfg)
    nomes = {p["name"] for p in d["projects"]}
    assert {"order-service", "payment-service", "shipping"} <= nomes
    assert d["integrations"]
    assert any(p["federation_only"] for p in d["projects"])


# ── busca cross-project ─────────────────────────────────────────────────
def test_scope_current_nao_cruza(hub: dict[str, Path]) -> None:
    out = search_scoped(load_config(hub["order"]), "pagamento", scope="current", limit=10)
    assert {r.project for r in out.results} == {"order-service"}


def test_scope_all_cruza_repositorios(hub: dict[str, Path]) -> None:
    out = search_scoped(load_config(hub["order"]), "cobranca pagamento", scope="all", limit=10)
    assert "payment-service" in {r.project for r in out.results}


def test_todo_resultado_carrega_project(hub: dict[str, Path]) -> None:
    out = search_scoped(load_config(hub["order"]), "pagamento", scope="all", limit=10)
    assert out.results
    for r in out.results:
        assert r.project and r.project != "current"


def test_scope_project_restringe(hub: dict[str, Path]) -> None:
    out = search_scoped(
        load_config(hub["order"]), "cobranca", scope="project:payment-service", limit=10
    )
    assert out.results
    assert {r.project for r in out.results} == {"payment-service"}


def test_projeto_nao_clonado_participa_pela_fatia(hub: dict[str, Path]) -> None:
    out = search_scoped(load_config(hub["order"]), "shipping quote frete", scope="all", limit=10)
    fed = [r for r in out.results if r.project == "shipping"]
    assert fed, "projeto só-federação devia participar da busca"
    assert all(r.metadata.get("federation_only") for r in fed)


def test_projeto_privado_invisivel_em_todo_scope(ws: dict[str, Path], tmp_path: Path) -> None:
    cfg = load_config(ws["order"])
    hub_mod.register(cfg, ws["pay"])
    conn = hub_mod.open_hub(cfg)
    conn.execute("UPDATE projects SET visibility = 'private' WHERE name = 'payment-service'")
    conn.commit()
    conn.close()
    hub_mod.sync(cfg)

    todos = search_scoped(cfg, "cobranca pagamento", scope="all", limit=10)
    assert "payment-service" not in {r.project for r in todos.results}

    explicito = search_scoped(cfg, "cobranca", scope="project:payment-service", limit=10)
    assert explicito.results == [], "nem `project:<nome>` explícito pode ver um private"


def test_sem_hub_orienta_o_usuario(ws: dict[str, Path]) -> None:
    with pytest.raises(UsageError, match="register"):
        search_scoped(load_config(ws["order"]), "x", scope="all")


def test_projeto_externo_recebe_penalidade(hub: dict[str, Path]) -> None:
    """Empatados, o projeto em que o dev está trabalhando é o mais útil."""
    cfg = load_config(hub["order"])
    cfg.hub.external_penalty = 0.1
    out = search_scoped(cfg, "pagamento cobranca", scope="all", limit=10)
    locais = [r.score for r in out.results if r.project == "order-service"]
    externos = [r.score for r in out.results if r.project != "order-service"]
    if locais and externos:
        assert max(locais) > max(externos)


def test_modelo_divergente_degrada_para_keyword(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    conn = hub_mod.open_hub(cfg)
    conn.execute("UPDATE projects SET status='degraded' WHERE name='payment-service'")
    conn.commit()
    conn.close()
    out = search_scoped(cfg, "cobranca", scope="all", limit=10)
    assert "payment-service" in out.degraded
    assert "keyword" in out.degraded["payment-service"]


def test_registry_json_e_escrito(hub: dict[str, Path]) -> None:
    cfg = load_config(hub["order"])
    path = hub_mod.hub_dir(cfg) / hub_mod.REGISTRY
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["projects"]) == 3
