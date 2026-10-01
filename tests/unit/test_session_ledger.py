"""`SessionLedger`: o que já foi entregue nesta sessão (RAGX-0159)."""

from __future__ import annotations

import threading

import pytest

from ragx.config import load_config
from ragx.context import format as fmt
from ragx.context.session import SessionLedger, from_config

pytestmark = pytest.mark.unit


class Relogio:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_mark_e_seen() -> None:
    led = SessionLedger()
    assert led.seen("a" * 32) is None
    led.mark("a" * 32, "src/a.py", 3, 9, 40)
    visto = led.seen("a" * 32)
    assert visto is not None and (visto.document_path, visto.start_line, visto.end_line, visto.tokens) == ("src/a.py", 3, 9, 40)
    led.mark("", "x", 1, 1, 1)  # id vazio não entra
    assert len(led) == 1


def test_ttl_com_relogio_falso() -> None:
    rel = Relogio()
    led = SessionLedger(ttl_s=60, clock=rel)
    led.mark("a" * 32, "a.py", 1, 2, 5)
    rel.t += 59
    assert led.seen("a" * 32) is not None
    rel.t += 2  # 61 s depois
    assert led.seen("a" * 32) is None
    assert len(led) == 0  # a entrada vencida some


def test_despeja_o_mais_antigo_ao_passar_do_limite() -> None:
    led = SessionLedger(max_entries=3)
    for i in range(5):
        led.mark(f"{i:032d}", "a.py", 1, 1, 1)
    assert len(led) == 3
    assert led.seen(f"{0:032d}") is None and led.seen(f"{1:032d}") is None
    assert led.seen(f"{4:032d}") is not None


def test_reentregar_renova_a_posicao() -> None:
    led = SessionLedger(max_entries=2)
    led.mark("a" * 32, "a.py", 1, 1, 1)
    led.mark("b" * 32, "b.py", 1, 1, 1)
    led.mark("a" * 32, "a.py", 1, 1, 1)  # a volta ao fim
    led.mark("c" * 32, "c.py", 1, 1, 1)  # despeja o b, não o a
    assert led.seen("a" * 32) is not None and led.seen("b" * 32) is None


def test_acesso_concorrente_nao_perde_nem_corrompe() -> None:
    led = SessionLedger(max_entries=10_000)

    def escreve(base: int) -> None:
        for i in range(500):
            led.mark(f"{base * 1000 + i:032d}", "a.py", 1, 1, 1)
            led.seen(f"{base * 1000 + i:032d}")

    threads = [threading.Thread(target=escreve, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(led) == 4000


def test_o_ledger_so_guarda_metadado_nunca_conteudo() -> None:
    led = SessionLedger()
    led.mark("a" * 32, "src/a.py", 1, 5, 12)
    entrada = led.seen("a" * 32)
    assert entrada is not None
    campos = set(entrada.__slots__)
    assert campos == {"chunk_id", "document_path", "start_line", "end_line", "tokens", "at"}


def test_from_config_respeita_session_dedupe(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = '[project]\nname = "t"\n'
    (tmp_path / "ragx.toml").write_text(base, encoding="utf-8")
    assert from_config(load_config(tmp_path)) is None  # desligado por padrão (RAGX-0159)
    (tmp_path / "ragx.toml").write_text(base + "\n[context]\nsession_dedupe = true\n", encoding="utf-8")
    led = from_config(load_config(tmp_path))
    assert led is not None and led.ttl_s == 45 * 60 and led.max_entries == 2000


def test_o_id_da_referencia_tem_o_mesmo_tamanho_do_fio() -> None:
    from ragx.mcp.tools import WIRE_ID_LEN

    assert fmt.REFERENCE_ID_CHARS == WIRE_ID_LEN


def test_a_linha_de_referencias_nao_carrega_conteudo() -> None:
    linha = fmt.references_line([("ab" * 16, "src/a.py", 3, 9), ("cd" * 16, "docs/x.md", 1, 4)])
    assert "src/a.py:3-9 [abababababab]" in linha and "docs/x.md:1-4 [cdcdcdcdcdcd]" in linha
    assert "get_chunk" in linha
