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


# ── dois estágios (RAGX-0152) ───────────────────────────────────────────
def _projeto_variado(raiz: Path) -> None:
    (raiz / ".gitignore").write_text("gerado/\n", encoding="utf-8")
    (raiz / "gerado").mkdir()
    (raiz / "gerado" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (raiz / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (raiz / "igual.py").write_text("y = 2\n", encoding="utf-8")  # `unchanged` pelo fingerprint
    (raiz / "binario.py").write_bytes(b"a\x00b" * 100)
    (raiz / "grande.py").write_text("z = 1\n" * 5000, encoding="utf-8")
    (raiz / ".env").write_text("SEGREDO=1\n", encoding="utf-8")
    (raiz / "vaza.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    (raiz / "sub").mkdir()
    (raiz / "sub" / "dentro.md").write_text("# Titulo\n\ntexto\n", encoding="utf-8")


def test_iter_files_e_a_composicao_dos_dois_estagios(tmp_path: Path) -> None:
    from ragx.walk import Candidate, iter_candidates, iter_files, read_candidate

    _projeto_variado(tmp_path)
    st = os.stat(tmp_path / "igual.py")
    fingerprints = {"igual.py": (st.st_size, st.st_mtime_ns)}
    gate = SecurityGate(tmp_path)
    kwargs = {"max_bytes": 10_000, "fingerprints": fingerprints}

    esperado = list(iter_files(tmp_path, gate, **kwargs))
    compostos = []
    candidatos = 0
    for item in iter_candidates(tmp_path, gate, **kwargs):
        if isinstance(item, Candidate):
            candidatos += 1
            lido = read_candidate(item, gate)
            if lido is not None:
                compostos.append(lido)
        else:
            compostos.append(item)
    assert compostos == esperado
    por_arquivo = {w.rel_path: w for w in esperado}
    assert por_arquivo["igual.py"].unchanged
    assert por_arquivo["binario.py"].decision.rule_id == "binary"
    assert por_arquivo["grande.py"].decision.rule_id == "too_large"
    assert por_arquivo[".env"].decision.verdict.name == "BLOCK"
    assert "gerado/x.py" not in por_arquivo
    # só chegam ao estágio de leitura os que precisam ser lidos
    assert 0 < candidatos < len(esperado)


def test_candidato_so_tem_dados_simples_e_nao_leva_conteudo(tmp_path: Path) -> None:
    import pickle

    from ragx.walk import Candidate, iter_candidates

    _projeto_variado(tmp_path)
    cands = [i for i in iter_candidates(tmp_path, SecurityGate(tmp_path), max_bytes=10_000) if isinstance(i, Candidate)]
    assert cands
    for c in cands:
        assert pickle.loads(pickle.dumps(c)) == c  # atravessa um processo sem custo
        assert not hasattr(c, "decision")


def test_read_candidate_de_arquivo_que_sumiu_devolve_none(tmp_path: Path) -> None:
    from ragx.walk import Candidate, iter_candidates, read_candidate

    _projeto_variado(tmp_path)
    gate = SecurityGate(tmp_path)
    alvo = next(i for i in iter_candidates(tmp_path, gate, max_bytes=10_000) if isinstance(i, Candidate) and i.rel == "ok.py")
    (tmp_path / "ok.py").unlink()
    assert read_candidate(alvo, gate) is None


def test_candidato_do_conhecimento_base_leva_o_prefixo_e_a_decisao_o_caminho_prefixado(tmp_path: Path) -> None:
    from ragx.walk import Candidate, iter_candidates, read_candidate

    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    gate = SecurityGate(tmp_path)
    cand = next(i for i in iter_candidates(tmp_path, gate, prefix="@base/x/") if isinstance(i, Candidate))
    assert cand.rel == "@base/x/a.py" and cand.inner == "a.py"
    lido = read_candidate(cand, gate)
    assert lido is not None and lido.rel_path == "@base/x/a.py" and lido.decision.path == "@base/x/a.py"
