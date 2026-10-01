"""`ragx ab`: o plano, o simulado e as guardas de custo (RAGX-0162)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.search import ab

pytestmark = pytest.mark.e2e
runner = CliRunner()

TOML = '[project]\nname = "t"\nid = "t"\n'


@pytest.fixture()
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    consultas = "\n".join(
        f'- query: "como funciona o modulo {i}"\n  relevant_paths: ["src/m{i}.py"]\n' for i in range(12)
    )
    (tmp_path / "queries.yaml").write_text(consultas, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RAGX_AB_REAL", raising=False)
    return tmp_path


@pytest.fixture()
def proibido(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Qualquer subprocesso iniciado pelo harness derruba o teste."""
    chamadas: list[str] = []

    def nunca(*a, **k):  # type: ignore[no-untyped-def]
        chamadas.append(str(a))
        raise AssertionError("o harness iniciou um subprocesso")

    monkeypatch.setattr(subprocess, "run", nunca)
    monkeypatch.setattr(subprocess, "Popen", nunca)
    return chamadas


def test_dry_run_e_o_padrao_imprime_o_plano_e_nao_inicia_subprocesso(proj: Path, proibido: list[str]) -> None:
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml"])
    assert r.exit_code == 0, r.output
    assert "nada foi executado" in r.output and "36" in r.output  # 12 tarefas × 3 braços × 1
    assert "RAGX_AB_REAL=1 ragx ab --execute --max-calls 36" in r.output.replace("\n", " ").replace("  ", " ")
    assert proibido == [] and not (proj / ".ragx" / "ab").exists()


def test_dry_run_json_lista_as_chamadas_planejadas(proj: Path, proibido: list[str]) -> None:
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--limit", "4", "--arms", "without,slim", "--json"])
    dados = json.loads(r.output)
    assert dados["dry_run"] is True and dados["calls"] == 8 and dados["by_arm"] == {"without": 4, "slim": 4}
    assert all("--strict-mcp-config" in c["argv"] for c in dados["planned"])
    assert not any("como funciona" in " ".join(c["argv"]) for c in dados["planned"])  # o prompt não está no argv


def test_simulate_roda_de_ponta_a_ponta_e_nao_apresenta_economia_como_real(proj: Path, proibido: list[str]) -> None:
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--simulate"])
    assert r.exit_code == 0, r.output
    assert "SIMULADO" in r.output and "SINTÉTICOS" in r.output and "(simulado)" in r.output
    arquivos = sorted((proj / ".ragx" / "ab").glob("*.json"))
    assert any(a.name.endswith("-simulado.json") for a in arquivos) and (proj / ".ragx" / "ab" / "latest.json").is_file()
    dados = json.loads((proj / ".ragx" / "ab" / "latest.json").read_text(encoding="utf-8"))
    assert dados["simulated"] is True and dados["method"]["simulated"] is True
    assert dados["method"]["tasks"] == 12 and dados["method"]["reps"] == 1
    assert proibido == []


def test_o_relatorio_nao_contem_texto_de_resposta(proj: Path, proibido: list[str]) -> None:
    runner.invoke(app, ["ab", "--queries", "queries.yaml", "--simulate"])
    texto = (proj / ".ragx" / "ab" / "latest.json").read_text(encoding="utf-8")
    campos = set(json.loads(texto)["results"][0])
    assert "result" not in campos and "text" not in campos and "answer" not in campos
    assert campos >= {"hit", "cited_paths", "input_tokens", "output_tokens", "cache_read_tokens", "cost_usd", "turns"}


def test_execute_sem_a_variavel_recusa_e_diz_o_que_gastaria(proj: Path, proibido: list[str]) -> None:
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--execute", "--max-calls", "100"])
    assert r.exit_code != 0
    saida = r.output + str(r.exception or "")
    assert "RAGX_AB_REAL=1" in saida and "36 chamadas reais" in saida and "cota" in saida
    assert proibido == []


def test_execute_sem_max_calls_ou_acima_do_teto_recusa(proj: Path, proibido: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAGX_AB_REAL", "1")
    sem_teto = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--execute"])
    assert sem_teto.exit_code != 0 and "--max-calls" in (sem_teto.output + str(sem_teto.exception or ""))
    baixo = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--execute", "--max-calls", "5"])
    assert baixo.exit_code != 0 and "36 chamadas" in (baixo.output + str(baixo.exception or ""))
    assert proibido == []


def test_simulate_e_execute_juntos_sao_recusados(proj: Path) -> None:
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--simulate", "--execute"])
    assert r.exit_code != 0


def test_braco_invalido_e_recusado(proj: Path) -> None:
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--arms", "without,enorme"])
    assert r.exit_code != 0


def test_o_execute_chama_o_runner_so_com_as_guardas(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Com as duas guardas (e um `claude` falso), o runner real é o `ClaudeRunner`: prova o encadeamento."""
    monkeypatch.setenv("RAGX_AB_REAL", "1")
    monkeypatch.setattr("shutil.which", lambda nome: "claude-falso")
    usados: list[str] = []

    def roda(self, call):  # type: ignore[no-untyped-def]
        usados.append(call.arm)
        return ab.ArmResult(call.arm, call.task_index, call.rep, hit=True, input_tokens=100)

    monkeypatch.setattr(ab.ClaudeRunner, "run", roda)
    monkeypatch.setattr(ab.ClaudeRunner, "version", lambda self: "2.1.0 (falso)")
    r = runner.invoke(app, ["ab", "--queries", "queries.yaml", "--limit", "2", "--execute", "--max-calls", "6"])
    assert r.exit_code == 0, r.output
    assert len(usados) == 6 and "SIMULADO" not in r.output
    dados = json.loads((proj / ".ragx" / "ab" / "latest.json").read_text(encoding="utf-8"))
    assert dados["simulated"] is False and dados["method"]["claude_version"] == "2.1.0 (falso)"
    assert (proj / ".ragx" / "ab" / "tmp" / "slim.mcp.json").is_file()
