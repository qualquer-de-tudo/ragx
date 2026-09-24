"""`ragx perf`: quanto tempo das sessões do Claude Code vai para o RAGX."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.perf import analyze_session, load_sessions, server_stats

pytestmark = pytest.mark.unit
runner = CliRunner()

T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC)


def _ts(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _prompt(at: float) -> dict:
    return {"type": "user", "timestamp": _ts(at), "message": {"role": "user", "content": "faça x"}}


def _assistant(at: float, *blocks: dict, msg_id: str = "m1") -> dict:
    return {
        "type": "assistant",
        "timestamp": _ts(at),
        "message": {"id": msg_id, "role": "assistant", "content": list(blocks)},
    }


def _use(tool_id: str, name: str) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": {}}


def _result(at: float, *tool_ids: str) -> dict:
    return {
        "type": "user",
        "timestamp": _ts(at),
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": t, "content": "ok"} for t in tool_ids
            ],
        },
    }


def _write(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_separa_tempo_do_ragx_do_resto(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s1.jsonl",
        [
            _prompt(0),
            # modelo leva 4 s e pede uma ferramenta do RAGX
            _assistant(4, _use("a", "mcp__ragx__get_playbook"), msg_id="m1"),
            # a ferramenta leva 2 s
            _result(6, "a"),
            # modelo leva 3 s e pede uma ferramenta que NÃO é do RAGX
            _assistant(9, _use("b", "Read"), msg_id="m2"),
            _result(10, "b"),
            _assistant(15, {"type": "text", "text": "pronto"}, msg_id="m3"),
        ],
    )
    s = analyze_session(f)
    assert s.calls == 1
    assert s.tool_ms == 2000
    assert s.model_ms == 4000  # só o turno que emitiu a chamada ao RAGX
    assert s.active_ms == 15000  # tudo menos o tempo do humano (o prompt não conta)
    assert s.overhead_ms == 6000
    assert s.per_tool["mcp__ragx__get_playbook"] == [2000]


def test_tempo_do_humano_nao_entra_como_ativo(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s2.jsonl",
        [
            _prompt(0),
            _assistant(5, {"type": "text", "text": "a"}, msg_id="m1"),
            _prompt(3600),  # a pessoa foi almoçar
            _assistant(3610, {"type": "text", "text": "b"}, msg_id="m2"),
        ],
    )
    s = analyze_session(f)
    assert s.active_ms == 15000
    assert s.calls == 0


def test_blocos_da_mesma_mensagem_viram_um_turno(tmp_path: Path) -> None:
    """O Claude Code grava uma linha por bloco; a latência é do turno inteiro."""
    f = _write(
        tmp_path / "s3.jsonl",
        [
            _prompt(0),
            _assistant(1, {"type": "thinking", "thinking": "..."}, msg_id="m1"),
            _assistant(6, _use("a", "mcp__ragx__search_hybrid"), msg_id="m1"),
            _result(7, "a"),
        ],
    )
    s = analyze_session(f)
    assert s.model_ms == 6000
    assert s.tool_ms == 1000


def test_paralelas_com_ferramenta_de_fora_nao_contam_como_ragx(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s4.jsonl",
        [
            _prompt(0),
            _assistant(2, _use("a", "mcp__ragx__refresh"), _use("b", "Bash"), msg_id="m1"),
            _result(9, "a", "b"),
        ],
    )
    s = analyze_session(f)
    assert s.calls == 1
    # o gap de 7 s pertence à mais lenta e não dá para saber qual foi
    assert s.tool_ms == 0


def test_pausa_longa_e_ociosidade(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "s5.jsonl",
        [
            _prompt(0),
            _assistant(2, _use("a", "mcp__ragx__refresh"), msg_id="m1"),
            _result(2 + 3 * 3600, "a"),  # máquina dormiu no meio
        ],
    )
    s = analyze_session(f)
    assert s.tool_ms == 0
    assert s.active_ms == 2000


def test_linha_corrompida_nao_derruba_a_analise(tmp_path: Path) -> None:
    f = tmp_path / "s6.jsonl"
    f.write_text(
        json.dumps(_prompt(0)) + "\n{quebrado\n" + json.dumps(_assistant(3, _use("a", "mcp__ragx__x"))) + "\n",
        encoding="utf-8",
    )
    assert analyze_session(f).calls == 1


def test_load_sessions_filtra_por_projeto_e_dias(tmp_path: Path) -> None:
    _write(tmp_path / "C--projects-alfa" / "a.jsonl", [_prompt(0), _assistant(1, _use("a", "mcp__ragx__x"))])
    _write(tmp_path / "C--projects-beta" / "b.jsonl", [_prompt(0), _assistant(1, _use("a", "mcp__ragx__x"))])
    todas = load_sessions(tmp_path)
    assert {s.project for s in todas} == {"C--projects-alfa", "C--projects-beta"}
    so_alfa = load_sessions(tmp_path, project="alfa")
    assert [s.project for s in so_alfa] == ["C--projects-alfa"]
    assert load_sessions(tmp_path, since=T0 + timedelta(days=1)) == []


def test_server_stats_le_o_jsonl_do_servidor(tmp_path: Path) -> None:
    p = tmp_path / "mcp.jsonl"
    linhas = [{"tool": "search_hybrid", "ms": ms} for ms in (10, 20, 30, 40)]
    linhas.append({"tool": "refresh", "ms": 5})
    p.write_text("\n".join(json.dumps(x) for x in linhas) + "\nlixo\n", encoding="utf-8")
    st = server_stats(p)
    assert st["search_hybrid"].n == 4
    assert st["search_hybrid"].p50 == 25
    assert st["refresh"].p50 == 5


def test_server_stats_sem_arquivo_e_vazio(tmp_path: Path) -> None:
    assert server_stats(tmp_path / "nao-existe.jsonl") == {}


def test_cli_perf_json(tmp_path: Path) -> None:
    _write(
        tmp_path / "C--projects-alfa" / "a.jsonl",
        [_prompt(0), _assistant(4, _use("a", "mcp__ragx__refresh")), _result(6, "a")],
    )
    r = runner.invoke(app, ["perf", "--dir", str(tmp_path), "--days", "3650", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados["summary"]["calls"] == 1
    assert dados["summary"]["overhead_ms"] == 6000
    assert dados["tools"][0]["tool"] == "mcp__ragx__refresh"
