"""Dedupe de sessão: chunk já entregue volta como referência (RAGX-0159)."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.context.engine import apply_session, build_context
from ragx.context.render import render
from ragx.context.session import SessionLedger
from ragx.indexing.pipeline import index_project
from ragx.mcp.server import KnowledgeAPI, build_server
from ragx.mcp.tools import BuildContextRequest

pytestmark = pytest.mark.integration

BASE = '[project]\nname = "demo"\nid = "demo"\n\n[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n'
# desligado por padrão (RAGX-0159): estes testes ligam de propósito
TOML = BASE + "\n[context]\nsession_dedupe = true\n"
SEGREDO = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def _arquivo(i: int, tema: str) -> str:
    corpo = "\n".join(f"        passo = '{tema} etapa {j}'  # {tema} {j}" for j in range(12))
    return f'class Servico{i}:\n    """Cuida de {tema} no modulo {i}."""\n\n    def rodar(self, x):\n{corpo}\n        return x\n'


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    for i, tema in enumerate(["autenticacao sessao", "fatura pagamento", "estoque armazem", "frete entrega"]):
        (tmp_path / f"m{i}.py").write_text(_arquivo(i, tema), encoding="utf-8")
    index_project(load_config(tmp_path))
    return tmp_path


def _tokens(pack) -> int:  # type: ignore[no-untyped-def]
    return pack.estimated_tokens


# ── o motor ─────────────────────────────────────────────────────────────
def test_segunda_consulta_traz_os_chunks_em_comum_como_referencia_e_entrega_menos(proj: Path) -> None:
    cfg = load_config(proj)
    ledger = SessionLedger()
    p1 = apply_session(build_context(cfg, "autenticacao sessao", budget=1500, use_cache=False), ledger)
    assert not p1.references and p1.fragments  # nada tinha sido entregue ainda

    completo = build_context(cfg, "autenticacao sessao do usuario", budget=1500, use_cache=False)
    p2 = apply_session(completo, ledger)
    assert p2.references, "a segunda consulta, sobreposta, devia trazer referências"
    assert _tokens(p2) < _tokens(completo)  # entrega MENOS tokens que sem o dedupe
    ids_ref = {r.chunk_id for r in p2.references}
    assert ids_ref.isdisjoint({f.chunk_id for f in p2.fragments})
    assert p2.stats["dedupe_refs"] == len(p2.references)
    assert p2.stats["dedupe_saved_tokens"] == _tokens(completo) - _tokens(p2) > 0
    md = render(p2, "markdown", title=False)
    assert "Já entregues nesta sessão" in md
    # o `estimated_tokens` conta o texto que sai, inclusive a linha de referências
    from ragx.tokens import count_tokens

    assert count_tokens(md) == p2.estimated_tokens


def test_o_pack_original_nao_e_alterado_e_o_cache_guarda_o_completo(proj: Path) -> None:
    cfg = load_config(proj)
    ledger = SessionLedger()
    original = build_context(cfg, "autenticacao sessao", budget=1500)
    n = len(original.fragments)
    apply_session(original, ledger)
    assert len(original.fragments) == n and not original.references
    apply_session(original, ledger)  # 2ª aplicação: tudo já entregue
    do_cache = build_context(cfg, "autenticacao sessao", budget=1500)
    assert len(do_cache.fragments) == n and not do_cache.references  # o cache segue completo


def test_ledger_vazio_ou_ausente_devolve_o_pack_como_veio(proj: Path) -> None:
    cfg = load_config(proj)
    pack = build_context(cfg, "autenticacao", budget=1000, use_cache=False)
    assert apply_session(pack, None) is pack
    assert apply_session(pack, SessionLedger()).fragments == pack.fragments


def test_chunk_editado_entre_as_chamadas_volta_como_conteudo(proj: Path) -> None:
    cfg = load_config(proj)
    ledger = SessionLedger()
    apply_session(build_context(cfg, "autenticacao sessao", budget=1500, use_cache=False), ledger)
    editado = _arquivo(0, "autenticacao sessao").replace("etapa 3", "etapa tres, editada")  # DENTRO do chunk
    (proj / "m0.py").write_text(editado, encoding="utf-8")
    index_project(cfg)  # o id do chunk deriva do conteúdo: o editado ganha id novo
    p = apply_session(build_context(cfg, "autenticacao sessao", budget=1500, use_cache=False), ledger)
    editados = [f for f in p.fragments if f.document_path == "m0.py"]
    assert editados, "o chunk editado devia voltar como conteúdo"
    assert all(r.document_path != "m0.py" or r.chunk_id not in {f.chunk_id for f in editados} for r in p.references)


def test_passado_o_ttl_o_chunk_volta_como_conteudo(proj: Path) -> None:
    class Relogio:
        t = 0.0

        def __call__(self) -> float:
            return self.t

    rel = Relogio()
    cfg = load_config(proj)
    ledger = SessionLedger(ttl_s=60, clock=rel)
    apply_session(build_context(cfg, "autenticacao sessao", budget=1500, use_cache=False), ledger)
    rel.t = 61
    p = apply_session(build_context(cfg, "autenticacao sessao", budget=1500, use_cache=False), ledger)
    assert not p.references


def test_se_as_referencias_custam_mais_que_o_conteudo_o_pack_segue_completo(proj: Path) -> None:
    from dataclasses import replace

    cfg = load_config(proj)
    pack = build_context(cfg, "autenticacao", budget=1000, use_cache=False)
    minusculo = tuple(replace(f, content="x", tokens=1) for f in pack.fragments[:1])
    pack = replace(pack, fragments=minusculo)
    ledger = SessionLedger()
    ledger.mark(minusculo[0].chunk_id, "a.py", 1, 1, 1)
    # o fragmento é minúsculo: referenciá-lo custa mais do que reenviá-lo, então fica completo
    assert apply_session(pack, ledger).references == ()


# ── o servidor MCP ──────────────────────────────────────────────────────
def test_mcp_segunda_chamada_traz_referencias_e_get_chunk_devolve_o_conteudo_integro(proj: Path) -> None:
    api = KnowledgeAPI(load_config(proj))
    a = api.build_context(BuildContextRequest(query="autenticacao sessao", tokens=1500))["data"]
    b = api.build_context(BuildContextRequest(query="autenticacao sessao do usuario", tokens=1500))["data"]
    assert "dedupe_refs" in b and b["dedupe_saved_tokens"] > 0
    assert b["estimated_tokens"] < a["estimated_tokens"] + 200
    assert "Já entregues nesta sessão" in b["markdown"]
    ids = re.findall(r"\[([0-9a-f]{12})\]", b["markdown"].split("Já entregues nesta sessão")[1])
    assert ids
    for cid in ids:
        r = api.get_chunk(cid)
        assert r["ok"] is True and r["data"]["content"].strip()  # SEMPRE o conteúdo, nunca referência


def test_mcp_json_traz_references_e_sem_dedupe_o_resultado_nao_muda(proj: Path) -> None:
    api = KnowledgeAPI(load_config(proj))
    api.build_context(BuildContextRequest(query="autenticacao sessao", tokens=1500))
    j = api.build_context(BuildContextRequest(query="autenticacao sessao do usuario", tokens=1500, format="json"))["data"]
    assert j["references"] and all({"chunk_id", "document_path", "lines"} <= r.keys() for r in j["references"])
    assert not ({r["chunk_id"] for r in j["references"]} & {f["chunk_id"] for f in j["fragments"]})

    (proj / "ragx.toml").write_text(BASE + "\n[context]\nsession_dedupe = false\n", encoding="utf-8")
    off = KnowledgeAPI(load_config(proj))
    x = off.build_context(BuildContextRequest(query="autenticacao sessao", tokens=1500))["data"]
    y = off.build_context(BuildContextRequest(query="autenticacao sessao", tokens=1500))["data"]
    assert x["markdown"] == y["markdown"] and "dedupe_refs" not in y and "Já entregues" not in y["markdown"]


def test_get_chunk_marca_como_entregue(proj: Path) -> None:
    api = KnowledgeAPI(load_config(proj))
    achados = api.search(__import__("ragx.mcp.tools", fromlist=["SearchRequest"]).SearchRequest(query="autenticacao"), mode="hybrid")["data"]["results"]
    cid = achados[0]["chunk_id"]
    assert api.get_chunk(cid)["ok"]
    assert len(api.ledger) == 1


def test_telemetria_registra_dedupe_refs_e_tokens_economizados(proj: Path) -> None:
    cfg = load_config(proj)
    server = build_server(cfg, allow_write=False)
    for q in ("autenticacao sessao", "autenticacao sessao do usuario"):
        asyncio.run(server.call_tool("build_context", {"query": q, "tokens": 1500}))
    linhas = [json.loads(x) for x in (cfg.state_dir / "logs" / "mcp.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "dedupe_refs" not in linhas[0]
    assert linhas[1]["dedupe_refs"] > 0 and linhas[1]["dedupe_saved_tokens"] > 0


# ── segurança ───────────────────────────────────────────────────────────
def test_o_ledger_aquecido_nao_deixa_o_segredo_chegar_a_nenhuma_resposta(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    (tmp_path / "ok.py").write_text(_arquivo(0, "autenticacao sessao"), encoding="utf-8")
    (tmp_path / "config.py").write_text(f'aws_secret_access_key = "{SEGREDO}"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    api = KnowledgeAPI(cfg)
    respostas = []
    for q in ("autenticacao sessao", "aws secret access key", "autenticacao sessao", "config"):
        respostas.append(json.dumps(api.build_context(BuildContextRequest(query=q, tokens=1500, format="json"))))
    assert SEGREDO not in "".join(respostas)
    assert len(api.ledger) > 0
    entradas = list(api.ledger._entries.values())
    assert SEGREDO not in repr(entradas)
