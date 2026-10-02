"""Harness de A/B de economia (RAGX-0162): nada aqui chama a API nem inicia o `claude`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.search import ab

pytestmark = pytest.mark.unit

TAREFAS = [ab.AbTask(f"pergunta {i}", (f"src/ragx/m{i}.py",)) for i in range(12)]


def _call(arm: str = "slim", i: int = 0, rep: int = 0) -> ab.Call:
    return ab.Call(arm, i, rep, TAREFAS[i], ("claude",), "p")


# ── o plano e o argv de cada braço ──────────────────────────────────────
def test_so_os_bracos_com_ragx_liberam_o_servidor_mcp(tmp_path) -> None:
    com = ab.build_argv("slim", tmp_path / "slim.mcp.json")
    assert com[com.index("--allowedTools") + 1] == "mcp__ragx"
    assert "--allowedTools" not in ab.build_argv("without", tmp_path / "without.mcp.json")


def test_permission_denials_do_claude_viram_contagem() -> None:
    res = ab.ArmResult("slim", 0, 0)
    ab._preencher(
        res,
        {"result": "x", "usage": {}, "permission_denials": [{"tool_name": "mcp__ragx__search_hybrid"}]},
        ab.AbTask("q", ("a.py",)),
    )
    assert res.permission_denials == 1


def test_with_hooks_so_o_braco_com_ragx_recebe_o_settings(tmp_path) -> None:
    com = ab.build_argv("slim", tmp_path / "slim.mcp.json", with_hooks=True)
    assert com[com.index("--settings") + 1] == str(tmp_path / "slim.settings.json")
    assert "--settings" not in ab.build_argv("without", tmp_path / "without.mcp.json", with_hooks=True)
    assert "--settings" not in ab.build_argv("slim", tmp_path / "slim.mcp.json")
    ab.write_mcp_files(["without", "slim"], tmp_path, tmp_path, with_hooks=True, command="ragx")
    assert not (tmp_path / "without.settings.json").exists()
    hooks = __import__("json").loads((tmp_path / "slim.settings.json").read_text(encoding="utf-8"))["hooks"]
    assert "claude hint" in hooks["SessionStart"][0]["hooks"][0]["command"]
    assert hooks["PreToolUse"][0]["matcher"] == "Grep|Glob"


def test_setting_sources_vai_igual_para_todos_os_bracos_e_some_quando_nao_pedido(tmp_path) -> None:
    for arm in ("without", "slim"):
        argv = ab.build_argv(arm, tmp_path / f"{arm}.mcp.json", setting_sources="project,local")
        i = argv.index("--setting-sources")
        assert argv[i + 1] == "project,local"
        assert "--bare" not in argv
    assert "--setting-sources" not in ab.build_argv("slim", tmp_path / "slim.mcp.json")


def test_argv_de_cada_braco_usa_config_estrita_e_o_prompt_vai_pelo_stdin(tmp_path: Path) -> None:
    pasta = tmp_path / "com espaço"  # caminho com espaço: um argumento só, sem aspas manuais
    argv = ab.build_argv("full", pasta / "full.mcp.json", claude="claude", model="sonnet", max_turns=8, isolate=True)
    assert argv[:4] == ("claude", "-p", "--output-format", "json")
    assert "--strict-mcp-config" in argv and argv[argv.index("--mcp-config") + 1] == str(pasta / "full.mcp.json")
    assert argv[argv.index("--model") + 1] == "sonnet" and argv[argv.index("--max-turns") + 1] == "8"
    assert "--bare" in argv and "--no-session-persistence" in argv
    assert not any("pergunta" in a for a in argv)  # o prompt NÃO está no argv
    sem = ab.build_argv("without", pasta / "without.mcp.json")
    assert "--model" not in sem and "--max-turns" not in sem and "--bare" not in sem


def test_mcp_config_do_braco_sem_ragx_e_vazio_e_os_outros_trazem_o_perfil(tmp_path: Path) -> None:
    assert ab.mcp_config("without", tmp_path) == {"mcpServers": {}}
    for perfil in ("full", "slim"):
        srv = ab.mcp_config(perfil, tmp_path)["mcpServers"]["ragx"]
        assert srv["env"] == {"RAGX_MCP_PROFILE": perfil}
        assert "mcp" in srv["args"] and "serve" in srv["args"] and str(tmp_path) in srv["args"]


def test_a_ordem_dos_bracos_gira_e_nenhum_e_sempre_o_primeiro() -> None:
    primeiros = {ab.order_for(i, ab.ARMS)[0] for i in range(6)}
    assert primeiros == set(ab.ARMS)
    assert all(sorted(ab.order_for(i, ab.ARMS)) == sorted(ab.ARMS) for i in range(6))


def test_o_plano_tem_tarefas_x_bracos_x_repeticoes_e_nao_escreve_nada(tmp_path: Path) -> None:
    pasta = tmp_path / "ab"
    chamadas = ab.plan(TAREFAS[:5], ab.ARMS, 2, tmp_path, pasta)
    assert len(chamadas) == 5 * 3 * 2
    assert not pasta.exists()  # planejar não grava o JSON do `--mcp-config`
    ab.write_mcp_files(ab.ARMS, tmp_path, pasta)
    assert json.loads((pasta / "slim.mcp.json").read_text(encoding="utf-8"))["mcpServers"]["ragx"]


# ── o acerto ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("src/ragx/m1.py", True),
        ("Os arquivos são:\n- `src\\ragx\\M1.py`\n- docs/x.md", True),  # barra do Windows e caixa
        ("./src/ragx/m1.py", True),
        ("src/ragx/outro.py", False),
        ("", False),
    ],
)
def test_hit_e_comparacao_de_texto_deterministica(texto: str, esperado: bool) -> None:
    assert ab.is_hit(texto, ("src/ragx/m1.py",)) is esperado


def test_cited_paths_so_guarda_tokens_de_caminho_nunca_a_resposta() -> None:
    cit = ab.cited_paths("Veja src/a.py e também docs/b.md. Nada mais.\nSegredo: sk_live_abc123")
    assert cit == ["src/a.py", "docs/b.md"]
    assert not any("segredo" in c for c in cit)


def test_o_resultado_preenchido_do_json_do_claude_nao_guarda_o_texto() -> None:
    res = ab.ArmResult("full", 0, 0)
    ab._preencher(res, {
        "result": "src/ragx/m0.py\nsk_live_SEGREDO_NA_RESPOSTA",
        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000},
        "total_cost_usd": 0.12, "num_turns": 4, "duration_ms": 9000,
    }, TAREFAS[0])
    assert res.hit and res.billable == 115 and res.gross == 1115 and res.turns == 4
    assert "SEGREDO" not in json.dumps(res.__dict__)


# ── o simulado ──────────────────────────────────────────────────────────
def test_simulated_runner_e_deterministico_por_semente_e_marcado() -> None:
    a, b, c = ab.SimulatedRunner(1), ab.SimulatedRunner(1), ab.SimulatedRunner(2)
    assert a.run(_call()) == b.run(_call())
    assert a.run(_call()).simulated is True and a.simulated is True
    assert a.run(_call()) != c.run(_call())


# ── a estatística ───────────────────────────────────────────────────────
def _par(i: int, sem: int, com: int, hit_sem: bool = True, hit_com: bool = True) -> list[ab.ArmResult]:
    return [
        ab.ArmResult("without", i, 0, hit=hit_sem, input_tokens=sem),
        ab.ArmResult("full", i, 0, hit=hit_com, input_tokens=com),
    ]


def test_economia_pareada_so_conta_onde_os_dois_braços_acharam_o_arquivo() -> None:
    rs = _par(0, 1000, 500) + _par(1, 1000, 100, hit_com=False) + _par(2, 1000, 900, hit_sem=False)
    assert ab.paired_savings(rs, "without", "full") == [0.5]  # a economia sem acerto não conta


def test_um_braco_com_erro_sai_da_conta() -> None:
    rs = _par(0, 1000, 500)
    rs[1].error = "timeout"
    assert ab.paired_savings(rs, "without", "full") == []


def test_menos_de_10_tarefas_ou_intervalo_que_cruza_zero_e_inconclusivo() -> None:
    poucas = [r for i in range(5) for r in _par(i, 1000, 500)]
    assert ab.summarize(poucas, ("without", "full"), 5)["comparisons"]["full_vs_without"]["label"] == "inconclusivo"

    muitas = [r for i in range(12) for r in _par(i, 1000, 500)]
    c = ab.summarize(muitas, ("without", "full"), 12)["comparisons"]["full_vs_without"]
    assert c["label"] == "economiza" and c["saving_median"] == 0.5 and c["ci95"][0] > 0

    ruido = [r for i in range(12) for r in _par(i, 1000, 1000 + (-1) ** i * 400)]
    assert ab.summarize(ruido, ("without", "full"), 12)["comparisons"]["full_vs_without"]["label"] == "inconclusivo"


def test_quartis_e_bootstrap_sao_deterministicos() -> None:
    v = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    assert ab.quartiles(v) == (0.25, 0.4, 0.55)
    assert ab.bootstrap_ci(v) == ab.bootstrap_ci(v)
    assert ab.quartiles([]) == (0.0, 0.0, 0.0) and ab.bootstrap_ci([]) == (0.0, 0.0)


def test_o_relatorio_traz_o_metodo_e_marca_o_simulado() -> None:
    chamadas = ab.plan(TAREFAS, ab.ARMS, 1, Path("."), Path("tmp"))
    rel = ab.run_ab(chamadas, ab.SimulatedRunner(), ab.ARMS, len(TAREFAS), {"model": "x", "tasks": 12, "reps": 1})
    dados = rel.to_json()
    assert dados["simulated"] is True and dados["method"]["simulated"] is True
    assert dados["method"]["claude_version"] == "simulado" and dados["method"]["tasks"] == 12
    assert set(dados["summary"]["arms"]) == set(ab.ARMS) and "full_vs_without" in dados["summary"]["comparisons"]
    assert len(dados["results"]) == len(chamadas)
    assert all(r["simulated"] for r in dados["results"])


def test_mcp_log_delta_conta_so_o_que_veio_depois(tmp_path: Path) -> None:
    log = tmp_path / "mcp.jsonl"
    log.write_text(json.dumps({"resp_tokens": 7}) + "\n", encoding="utf-8")
    antes = log.stat().st_size
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"resp_tokens": 100}) + "\n" + json.dumps({"resp_tokens": 50}) + "\n")
    assert ab._mcp_log_delta(log, antes) == (2, 150)
    assert ab._mcp_log_delta(None, 0) == (0, 0) and ab._mcp_log_delta(tmp_path / "x", 0) == (0, 0)
