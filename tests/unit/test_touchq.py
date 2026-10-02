"""`touchq`: a fila de arquivos tocados (RAGX-0141)."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from ragx.indexing import touchq

pytestmark = pytest.mark.unit


def test_enqueue_e_claim_com_dedup(tmp_path: Path) -> None:
    sd = tmp_path / ".ragx"
    assert touchq.enqueue(sd, ["a.py", "src/b.py", "a.py", "src\\b.py"]) == 4
    assert touchq.pending(sd) == ["a.py", "src/b.py"]  # lê sem consumir, deduplicado
    assert touchq.is_pending(sd)
    lote = touchq.claim(sd)
    assert lote is not None and lote.paths == ["a.py", "src/b.py"]
    assert not touchq.is_pending(sd)  # a fila foi tomada
    lote.done()
    assert list(sd.glob("*.claimed")) == []


def test_claim_de_fila_vazia_ou_inexistente_e_none(tmp_path: Path) -> None:
    assert touchq.claim(tmp_path / ".ragx") is None
    (tmp_path / ".ragx").mkdir()
    (tmp_path / ".ragx" / touchq.QUEUE_NAME).write_text("\n\n", encoding="utf-8")
    assert touchq.claim(tmp_path / ".ragx") is None


def test_give_back_devolve_o_lote(tmp_path: Path) -> None:
    sd = tmp_path / ".ragx"
    touchq.enqueue(sd, ["a.py", "b.py"])
    lote = touchq.claim(sd)
    assert lote is not None
    lote.give_back()
    assert touchq.pending(sd) == ["a.py", "b.py"]
    assert list(sd.glob("*.claimed")) == []


def test_dois_claim_concorrentes_devolvem_conjuntos_disjuntos(tmp_path: Path) -> None:
    sd = tmp_path / ".ragx"
    touchq.enqueue(sd, [f"f{i}.py" for i in range(50)])
    resultados: list[list[str]] = []

    def consumir() -> None:
        lote = touchq.claim(sd)
        resultados.append(lote.paths if lote else [])

    threads = [threading.Thread(target=consumir) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Sob carga, quem perde a disputa pelo arquivo devolve vazio (e todos podem perder): o que importa é que NINGUÉM
    # receba o mesmo caminho e que nada se perca; o que sobrou continua na fila e o próximo `claim` o pega.
    while (resto := touchq.claim(sd)) is not None:
        resultados.append(resto.paths)
    todos = [p for r in resultados for p in r]
    assert len(todos) == len(set(todos)) == 50  # ninguém recebeu o mesmo caminho


def test_teto_de_lote_devolve_a_sobra_para_a_fila(tmp_path: Path) -> None:
    sd = tmp_path / ".ragx"
    touchq.enqueue(sd, [f"f{i}.py" for i in range(7)])
    lote = touchq.claim(sd, max_batch=3)
    assert lote is not None and len(lote.paths) == 3
    assert touchq.pending(sd) == [f"f{i}.py" for i in range(3, 7)]


def test_linhas_com_crlf_e_lixo(tmp_path: Path) -> None:
    sd = tmp_path / ".ragx"
    sd.mkdir()
    (sd / touchq.QUEUE_NAME).write_bytes(b"a.py\r\nb.py\r\n\r\n   \r\nc.py")
    assert touchq.pending(sd) == ["a.py", "b.py", "c.py"]
    # linha com quebra ou comprida demais não vira entrada
    assert touchq.enqueue(sd, ["bom.py", "ruim\nlinha.py", "x" * 5000]) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="maiúsculas só são ignoradas no Windows")
def test_no_windows_maiusculas_sao_a_mesma_entrada(tmp_path: Path) -> None:
    sd = tmp_path / ".ragx"
    touchq.enqueue(sd, ["Src/A.py", "src/a.py"])
    assert len(touchq.pending(sd)) == 1


def test_resolve_aceita_absoluto_e_relativo_e_normaliza(tmp_path: Path) -> None:
    raiz = tmp_path / "proj"
    (raiz / "src").mkdir(parents=True)
    (raiz / "src" / "b.py").write_text("x\n", encoding="utf-8")
    assert touchq.resolve(raiz, raiz / "src" / "b.py") == "src/b.py"
    assert touchq.resolve(raiz, "src/b.py") == "src/b.py"
    assert touchq.resolve(raiz, "src\\b.py") in ("src/b.py", None)  # `\` só é separador no Windows
    assert touchq.resolve(raiz, "./src/../src/b.py") == "src/b.py"
    if sys.platform == "win32":
        assert touchq.resolve(raiz, str(raiz).upper() + "\\SRC\\B.PY") is not None  # `C:\a\b.py` == `a/b.py`


def test_resolve_recusa_o_que_escapa_da_raiz(tmp_path: Path) -> None:
    raiz = tmp_path / "proj"
    raiz.mkdir()
    (tmp_path / "fora.txt").write_text("x\n", encoding="utf-8")
    assert touchq.resolve(raiz, "../fora.txt") is None
    assert touchq.resolve(raiz, tmp_path / "fora.txt") is None
    assert touchq.resolve(raiz, raiz) is None  # a própria raiz não é arquivo
    assert touchq.resolve(raiz, "src/../../fora.txt") is None


def test_resolve_recusa_link_para_fora(tmp_path: Path) -> None:
    raiz = tmp_path / "proj"
    fora = tmp_path / "fora"
    raiz.mkdir()
    fora.mkdir()
    (fora / "s.py").write_text("x\n", encoding="utf-8")
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(fora), str(raiz / "linkout"))
    else:
        try:
            (raiz / "linkout").symlink_to(fora, target_is_directory=True)
        except OSError:
            pytest.skip("sem permissão para criar symlink")
    assert touchq.resolve(raiz, "linkout/s.py") is None


def test_touchq_nao_le_arquivo_do_projeto() -> None:
    """A fila lida só com NOMES: ler o conteúdo seria contornar o Security Gate."""
    fonte = Path(touchq.__file__).read_text(encoding="utf-8")
    assert "read_bytes" not in fonte
    # a única leitura de texto é da própria fila (`_ler` e o `claim`)
    assert fonte.count("read_text(") == 1
