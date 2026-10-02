"""`scope` no MCP: honrado ou recusado, nunca ignorado em silêncio — e sem abrir o hub.

`search_hybrid`, `search_knowledge` e `build_context` aceitavam `scope` e o
descartavam: `scope="all"` consultava só o projeto atual e o agente acreditava
ter consultado o conjunto. A regra que não pode regredir: projeto `private` é
invisível em qualquer escopo, e `project:<privado>` responde exatamente como
`project:<inexistente>`.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0137-*.md`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from test_federation import ORDER, PAYMENT_ROUTES, PAYMENT_SERVICE, SHIPPING, _make

from ragx.config import load_config
from ragx.federation import hub as hub_mod
from ragx.federation import slice as fed_slice
from ragx.mcp.server import KnowledgeAPI
from ragx.mcp.tools import BuildContextRequest, SearchRequest

pytestmark = pytest.mark.security


@pytest.fixture
def mundo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setenv("RAGX_HUB_PATH", str(tmp_path / "hub"))
    pay = _make(tmp_path / "payment-service", "payment-service",
                {"routes.py": PAYMENT_ROUTES, "service.py": PAYMENT_SERVICE})
    ship = _make(tmp_path / "shipping", "shipping", {"routes.py": SHIPPING})
    order = _make(tmp_path / "order-service", "order-service", {"order.py": ORDER})
    cfg = load_config(order)
    fed = tmp_path / "shipping.fed.json"
    fed_slice.export_file(load_config(ship), fed)
    hub_mod.register(cfg, order)
    hub_mod.register(cfg, pay)
    hub_mod.register(cfg, from_federation=fed)
    hub_mod.sync(cfg)
    return {"order": order, "pay": pay, "ship": ship, "root": tmp_path}


def _api(mundo: dict[str, Path]) -> KnowledgeAPI:
    return KnowledgeAPI(load_config(mundo["order"]))


def _projetos(resp: dict) -> set[str]:
    assert resp["ok"], resp
    # `current` leva a origem em `data.project`; o federado, em cada hit
    return {h.get("project", resp["data"].get("project")) for h in resp["data"]["results"]}


def _privar(mundo: dict[str, Path]) -> None:
    cfg = load_config(mundo["order"])
    conn = hub_mod.open_hub(cfg)
    conn.execute("UPDATE projects SET visibility = 'private' WHERE name = 'payment-service'")
    conn.commit()
    conn.close()
    hub_mod.sync(cfg)


# ── scope honrado ───────────────────────────────────────────────────────
def test_scope_all_cruza_projetos_pelo_mcp(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).search(SearchRequest(query="cobranca pagamento", scope="all"), "hybrid")
    assert "payment-service" in _projetos(resp), "scope=all era ignorado e só o projeto atual respondia"
    assert resp["data"]["scope"] == "all" and "payment-service" in resp["data"]["projects"]


def test_scope_project_restringe_pelo_mcp(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).search(
        SearchRequest(query="cobranca", scope="project:payment-service"), "hybrid"
    )
    assert _projetos(resp) == {"payment-service"}


def test_scope_current_nao_cruza_pelo_mcp(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).search(SearchRequest(query="pagamento", scope="current"), "hybrid")
    assert _projetos(resp) == {"order-service"}
    assert "scope" not in resp["data"]  # o formato de `current` não mudou


def test_path_glob_e_respeitado_em_scope_all(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).search(
        SearchRequest(query="cobranca pagamento", scope="all", path_glob="service.py"), "hybrid"
    )
    assert resp["ok"]
    do_outro = [h for h in resp["data"]["results"] if h["project"] == "payment-service"]
    assert do_outro
    assert all(h["document_path"].endswith("service.py") for h in do_outro)


def test_path_glob_perigoso_e_recusado_em_scope_all(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).search(
        SearchRequest(query="x", scope="all", path_glob="../fora"), "hybrid"
    )
    assert not resp["ok"] and resp["error"]["code"] == "invalid_path"


# ── build_context ───────────────────────────────────────────────────────
def test_build_context_com_project_monta_o_pack_do_outro_projeto(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).build_context(
        BuildContextRequest(query="cobranca pagamento", tokens=800, scope="project:payment-service",
                            format="json")
    )
    assert resp["ok"], resp
    data = resp["data"]
    assert data["project"] == "payment-service"
    assert data["fragments"] and all(f["project"] == "payment-service" for f in data["fragments"])
    assert all(("service.py" in f["document_path"] or "routes.py" in f["document_path"]
                or f["document_path"].endswith(".toml")) for f in data["fragments"])


def test_build_context_all_e_recusado_com_motivo(mundo: dict[str, Path]) -> None:
    resp = _api(mundo).build_context(BuildContextRequest(query="x pagamento", scope="all"))
    assert not resp["ok"] and resp["error"]["code"] == "scope_unsupported"
    assert "project:<nome>" in resp["error"]["message"]


def test_build_context_de_projeto_registrado_so_por_federacao_e_recusado(
    mundo: dict[str, Path],
) -> None:
    resp = _api(mundo).build_context(BuildContextRequest(query="frete", scope="project:shipping"))
    assert not resp["ok"] and resp["error"]["code"] == "scope_unsupported"
    assert "contratos" in resp["error"]["message"]


def test_nenhuma_ferramenta_aceita_scope_e_o_descarta(
    mundo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem hub, `scope="all"` não pode devolver resultado do projeto atual como se
    fosse do conjunto: ou dá erro explícito, ou o resultado vem marcado com `scope`."""
    import asyncio

    from ragx.mcp.server import build_server

    sem_hub = tmp_path / "sozinho"
    _make(sem_hub, "sozinho", {"a.py": "def a():\n    '''cobranca'''\n    return 1\n"})
    monkeypatch.setenv("RAGX_HUB_PATH", str(tmp_path / "hub-que-nao-existe"))
    cfg = load_config(sem_hub)
    api = KnowledgeAPI(cfg)
    tools = {t.name: t for t in asyncio.run(build_server(cfg, profile="full").list_tools())}
    com_scope = [n for n, t in tools.items() if "scope" in json.dumps(t.input_schema)]
    assert {"search_hybrid", "search_knowledge", "build_context"} <= set(com_scope)
    respostas = {
        "search_hybrid": api.search(SearchRequest(query="cobranca", scope="all"), "hybrid"),
        "search_knowledge": api.search(SearchRequest(query="cobranca", scope="all"), "semantic"),
        "build_context": api.build_context(BuildContextRequest(query="cobranca", scope="all")),
    }
    assert set(com_scope) <= set(respostas), f"ferramenta nova com scope sem teste: {com_scope}"
    for nome in com_scope:
        r = respostas[nome]
        assert (not r["ok"]) or r["data"].get("scope") == "all", (nome, r)


# ── projeto privado ─────────────────────────────────────────────────────
def test_privado_nunca_aparece_em_nenhum_scope(mundo: dict[str, Path]) -> None:
    _privar(mundo)
    api = _api(mundo)
    for modo in ("hybrid", "semantic"):
        todos = api.search(SearchRequest(query="cobranca pagamento", scope="all"), modo)
        assert "payment-service" not in _projetos(todos)
    ctx = api.build_context(
        BuildContextRequest(query="cobranca pagamento", scope="project:payment-service")
    )
    assert not ctx["ok"]


def test_privado_e_inexistente_respondem_igual(mundo: dict[str, Path]) -> None:
    _privar(mundo)
    api = _api(mundo)
    a = api.search(SearchRequest(query="cobranca", scope="project:payment-service"), "hybrid")
    b = api.search(SearchRequest(query="cobranca", scope="project:nao-existe"), "hybrid")
    assert not a["ok"] and not b["ok"]
    assert a["error"]["code"] == b["error"]["code"] == "not_found"
    assert a["error"]["message"].replace("payment-service", "X") == b["error"]["message"].replace(
        "nao-existe", "X"
    )
    ca = api.build_context(BuildContextRequest(query="x", scope="project:payment-service"))
    cb = api.build_context(BuildContextRequest(query="x", scope="project:nao-existe"))
    assert not ca["ok"] and not cb["ok"]
    assert ca["error"]["code"] == cb["error"]["code"] == "not_found"
    assert ca["error"]["message"].replace("payment-service", "X") == cb["error"]["message"].replace(
        "nao-existe", "X"
    )


def test_nenhum_segredo_sai_por_scope_all(mundo: dict[str, Path]) -> None:
    from ragx.indexing.pipeline import index_project

    (mundo["pay"] / ".env").write_text(
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n", encoding="utf-8"
    )
    index_project(load_config(mundo["pay"]))
    resp = _api(mundo).search(SearchRequest(query="wJalrXUtnFEMI AWS_SECRET", scope="all"), "hybrid")
    assert "wJalrXUtnFEMI" not in json.dumps(resp)
