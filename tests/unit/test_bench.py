"""O harness do benchmark de modelos (RAGX-0169): status sem baixar nada, loopback e estimativa."""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import UsageError
from ragx.search import bench
from ragx.search.bench import Candidate

pytestmark = pytest.mark.unit


@pytest.fixture
def cfg(tmp_path: Path):
    (tmp_path / "ragx.toml").write_text('[project]\nname = "b"\nid = "b"\n', encoding="utf-8")
    return load_config(tmp_path)


def test_probe_do_ollama_distingue_presente_ausente_e_daemon_fora(cfg) -> None:
    c = Candidate("nomic", "ollama", "nomic-embed-text", 768)
    assert bench.probe(c, cfg, ollama_tags=lambda url: ["nomic-embed-text:latest", "outro:1b"])[0] == "disponivel"
    assert bench.probe(c, cfg, ollama_tags=lambda url: ["so-outro:1b"]) == ("ausente", "não está no Ollama")
    status, detalhe = bench.probe(c, cfg, ollama_tags=lambda url: None)
    assert status == "ausente" and "fora do ar" in detalhe
    com_tag = Candidate("q", "ollama", "qwen3-embedding:0.6b", 1024)
    assert bench.probe(com_tag, cfg, ollama_tags=lambda url: ["qwen3-embedding:0.6b"])[0] == "disponivel"


def test_probe_do_fastembed_olha_o_cache_e_nunca_carrega_nem_baixa(cfg, tmp_path: Path) -> None:
    c = Candidate("minilm", "fastembed", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 384)
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    assert bench.probe(c, cfg, cache_dirs=[vazio])[0] == "ausente"
    pasta = bench._hf_dir(c.model, "embedding")
    assert pasta and pasta.startswith("models--")
    cheio = tmp_path / "cheio"
    (cheio / pasta).mkdir(parents=True)
    assert bench.probe(c, cfg, cache_dirs=[cheio])[0] == "disponivel"
    desconhecido = Candidate("x", "fastembed", "ninguem/nao-existe", 8)
    assert bench.probe(desconhecido, cfg, cache_dirs=[cheio])[0] == "incompativel"


def test_hashing_e_sempre_disponivel_e_provider_estranho_e_incompativel(cfg) -> None:
    assert bench.probe(Candidate("h", "hashing", "hashing", 64), cfg)[0] == "disponivel"
    assert bench.probe(Candidate("z", "nuvem", "x", 8), cfg)[0] == "incompativel"


@pytest.mark.parametrize("url", ["https://api.exemplo.com", "http://10.0.0.5:11434", "http://meu-servidor.local"])
def test_base_url_que_nao_e_loopback_e_recusada(url: str) -> None:
    with pytest.raises(UsageError, match="própria máquina"):
        bench.assert_loopback(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"])
def test_loopback_passa(url: str) -> None:
    bench.assert_loopback(url)


def test_o_probe_do_ollama_recusa_um_host_remoto_antes_de_qualquer_chamada() -> None:
    with pytest.raises(UsageError):
        bench._ollama_tags("http://exemplo.com:11434")


def test_licenca_nao_comercial_e_marcada() -> None:
    assert Candidate("r", "fastembed", "jinaai/jina-reranker-v2-base-multilingual", 0, "reranker", "cc-by-nc-4.0").non_commercial
    assert not Candidate("r", "fastembed", "x", 0, "reranker", "apache-2.0").non_commercial


def test_o_arquivo_de_candidatos_do_repo_carrega_e_traz_o_atual_e_o_nomic() -> None:
    raiz = Path(__file__).resolve().parents[2]
    c = {x.name: x for x in bench.load_candidates(raiz / "tests" / "eval" / "models.yaml")}
    assert c["minilm-atual"].provider == "fastembed" and c["ollama-nomic-embed-text"].provider == "ollama"
    assert any(x.kind == "reranker" for x in c.values())


def test_a_estimativa_acima_de_20_min_exige_force_slow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from ragx.cli.main import app
    from ragx.indexing.pipeline import index_project

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "b"\nid = "b"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n', encoding="utf-8"
    )
    (tmp_path / "a.py").write_text("def f(x):\n    total = x\n    total += 1\n    total += 2\n    return total\n", encoding="utf-8")
    index_project(load_config(tmp_path))
    (tmp_path / "c.yaml").write_text("- name: h\n  provider: hashing\n  model: hashing\n  dim: 64\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bench, "estimate_seconds", lambda cfg, c, sample=64: 3 * 3600.0)
    r = CliRunner().invoke(app, ["bench", "models", "--candidates", "c.yaml"])
    assert r.exit_code != 0 and "--force-slow" in str(r.exception)
