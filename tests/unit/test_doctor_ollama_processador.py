"""`ragx doctor` informa se o Ollama usa GPU ou CPU, sem nunca falhar por isso."""

from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from ragx.cli.commands.doctor import _embedder_status

TAGS = json.dumps({"models": [{"name": "nomic-embed-text:latest"}]})


class _Resp(io.BytesIO):
    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *a: object) -> None:
        return None


def _cfg(provider: str = "ollama") -> SimpleNamespace:
    emb = SimpleNamespace(
        provider=provider, model="nomic-embed-text", dim=768, base_url="http://localhost:11434"
    )
    return SimpleNamespace(embedding=emb)


def _rede(monkeypatch: pytest.MonkeyPatch, ps: object) -> list[str]:
    """`ps` e um dict (JSON de /api/ps), texto cru, ou uma excecao a levantar."""
    chamadas: list[str] = []

    def fake(url: str, timeout: float = 0) -> _Resp:
        chamadas.append(url)
        if url.endswith("/api/tags"):
            return _Resp(TAGS.encode())
        if isinstance(ps, Exception):
            raise ps
        corpo = ps if isinstance(ps, str) else json.dumps(ps)
        return _Resp(corpo.encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return chamadas


def _linhas() -> tuple[list[tuple[str, str, bool]], object]:
    rows: list[tuple[str, str, bool]] = []

    def row(label: str, value: str, ok: bool, hint: list[str] | None = None) -> bool:
        rows.append((label, value, ok))
        return ok

    return rows, row


def _rodar(monkeypatch: pytest.MonkeyPatch, ps: object) -> tuple[bool, list[tuple[str, str, bool]]]:
    _rede(monkeypatch, ps)
    rows, row = _linhas()
    ok = _embedder_status(_cfg(), row)
    return ok, rows


def _proc(rows: list[tuple[str, str, bool]]) -> tuple[str, str, bool]:
    achadas = [r for r in rows if r[0] == "Ollama"]
    assert len(achadas) == 1
    return achadas[0]


def test_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    ps = {"models": [{"name": "nomic-embed-text:latest", "size_vram": 308 * 1024 * 1024}]}
    ok, rows = _rodar(monkeypatch, ps)
    assert ok is True
    assert _proc(rows) == ("Ollama", "GPU (308 MB de VRAM)", True)


def test_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    ps = {"models": [{"name": "nomic-embed-text:latest", "size_vram": 0}]}
    ok, rows = _rodar(monkeypatch, ps)
    assert ok is True
    assert _proc(rows) == ("Ollama", "CPU", True)


def test_modelo_sem_tag_casa_com_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    ps = {"models": [{"name": "nomic-embed-text", "size_vram": 1024 * 1024 * 10}]}
    _, rows = _rodar(monkeypatch, ps)
    assert _proc(rows)[1] == "GPU (10 MB de VRAM)"


def test_modelo_nao_carregado(monkeypatch: pytest.MonkeyPatch) -> None:
    for ps in ({"models": []}, {"models": [{"name": "outro:latest", "size_vram": 5}]}):
        ok, rows = _rodar(monkeypatch, ps)
        assert ok is True
        assert _proc(rows) == (
            "Ollama",
            "processador ainda não medido (nenhum modelo carregado)",
            True,
        )


@pytest.mark.parametrize(
    "ps",
    [
        urllib.error.URLError("boom"),
        TimeoutError(),
        "isto nao e json",
        ["lista", "inesperada"],
        {"models": "nao-e-lista"},
        {"models": [{"name": "nomic-embed-text:latest", "size_vram": "muito"}]},
    ],
)
def test_erro_ou_json_inesperado(monkeypatch: pytest.MonkeyPatch, ps: object) -> None:
    ok, rows = _rodar(monkeypatch, ps)
    assert ok is True
    assert _proc(rows) == ("Ollama", "não foi possível consultar o processador", True)


def test_nunca_muda_o_resultado_do_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    for ps in (
        {"models": [{"name": "nomic-embed-text", "size_vram": 9}]},
        {"models": []},
        TimeoutError(),
    ):
        ok, rows = _rodar(monkeypatch, ps)
        assert ok is True
        assert all(r[2] for r in rows if r[0] == "Ollama")
        assert next(r for r in rows if r[0] == "Embedder")[2] is True


def test_sem_linha_extra_quando_a_api_nao_responde(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(url: str, timeout: float = 0) -> _Resp:
        raise urllib.error.URLError("recusada")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    rows, row = _linhas()
    assert _embedder_status(_cfg(), row) is False
    assert not [r for r in rows if r[0] == "Ollama"]


def test_sem_linha_extra_quando_o_modelo_esta_ausente(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(url: str, timeout: float = 0) -> _Resp:
        return _Resp(json.dumps({"models": [{"name": "outro:latest"}]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    rows, row = _linhas()
    assert _embedder_status(_cfg(), row) is False
    assert not [r for r in rows if r[0] == "Ollama"]


def test_outro_provider_nao_consulta_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(*a: object, **k: object) -> _Resp:
        raise AssertionError("nao deveria chamar a rede")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    rows, row = _linhas()
    assert _embedder_status(_cfg("fastembed"), row) is True
    assert not [r for r in rows if r[0] == "Ollama"]
