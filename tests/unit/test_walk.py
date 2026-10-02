"""`scan_fingerprints` e `_walk` (RAGX-0147)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ragx.security.gate import SecurityGate
from ragx.walk import scan_fingerprints

pytestmark = pytest.mark.unit


@pytest.fixture()
def arvore(tmp_path: Path) -> Path:
    (tmp_path / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")
    for d in ("a", "a/b", "Zeta", "build"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    for f in ("a/x.py", "a/b/y.py", "Zeta/z.py", "raiz.py", "build/gerado.py", "a/app.log"):
        (tmp_path / f).write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def test_com_e_sem_cache_de_veredito_o_resultado_e_o_mesmo(arvore: Path) -> None:
    gate = SecurityGate(arvore)
    sem = scan_fingerprints(arvore, gate)
    cache: dict[str, bool] = {}
    com1 = scan_fingerprints(arvore, gate, False, cache)
    com2 = scan_fingerprints(arvore, gate, False, cache)  # agora com o cache cheio
    assert sem == com1 == com2
    assert "build/gerado.py" not in sem and "a/app.log" not in sem
    assert cache["a/app.log"] is True and cache["raiz.py"] is False


def test_arquivo_novo_calcula_o_veredito_e_entra(arvore: Path) -> None:
    gate = SecurityGate(arvore)
    cache: dict[str, bool] = {}
    scan_fingerprints(arvore, gate, False, cache)
    (arvore / "a" / "novo.py").write_text("y = 2\n", encoding="utf-8")
    (arvore / "a" / "novo.log").write_text("y = 2\n", encoding="utf-8")
    out = scan_fingerprints(arvore, gate, False, cache)
    assert "a/novo.py" in out and "a/novo.log" not in out


def test_o_tamanho_e_o_mtime_batem_com_os_stat(arvore: Path) -> None:
    out = scan_fingerprints(arvore, SecurityGate(arvore))
    st = os.stat(arvore / "a" / "x.py")
    assert out["a/x.py"] == (st.st_size, st.st_mtime_ns)


def test_caminhos_visitados_incluem_todas_as_pastas_nao_ignoradas(arvore: Path) -> None:
    assert set(scan_fingerprints(arvore, SecurityGate(arvore))) == {
        ".gitignore", "a/x.py", "a/b/y.py", "Zeta/z.py", "raiz.py",
    }
