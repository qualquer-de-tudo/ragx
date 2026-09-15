"""Suíte de segurança — BLOQUEANTE.

A fixture é o artefato de teste mais importante do repositório e estes testes
governam o avanço de todas as fases: cada superfície ainda inexistente está
marcada xfail, e virar cada xfail em pass é DoD da fase correspondente.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.secrets_under_test import (
    FIXTURE_ROOT,
    MUST_BLOCK,
    MUST_INDEX,
    MUST_REDACT,
    SECRETS_UNDER_TEST,
    leaked,
)
from ragx.core.models import Verdict
from ragx.security.gate import SecurityGate

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def gate() -> SecurityGate:
    return SecurityGate(FIXTURE_ROOT, policy="strict")


def _walk() -> list[str]:
    return [
        p.relative_to(FIXTURE_ROOT).as_posix()
        for p in sorted(FIXTURE_ROOT.rglob("*"))
        if p.is_file()
    ]


def _admit_all(gate: SecurityGate) -> dict[str, object]:
    out = {}
    for rel in _walk():
        raw = (FIXTURE_ROOT / rel).read_bytes()
        out[rel] = gate.admit(rel, raw)
    return out


# ── O teste central: nenhum segredo atravessa o gate ────────────────────
def test_nenhum_segredo_no_conteudo_admitido(gate: SecurityGate) -> None:
    for rel, d in _admit_all(gate).items():
        if d.content:
            assert leaked(d.content) == [], f"{rel} vazou: {leaked(d.content)}"


@pytest.mark.parametrize("rel", MUST_BLOCK)
def test_arquivos_sensiveis_sao_bloqueados(gate: SecurityGate, rel: str) -> None:
    raw = (FIXTURE_ROOT / rel).read_bytes()
    d = gate.admit(rel, raw)
    assert d.verdict is Verdict.BLOCK, f"{rel} deveria ser BLOCK, veio {d.verdict}"
    assert d.content is None


# ── Ausência de falso negativo: um gate que bloqueia tudo é inútil ──────
@pytest.mark.parametrize("rel", MUST_INDEX)
def test_arquivos_legitimos_continuam_indexados(gate: SecurityGate, rel: str) -> None:
    raw = (FIXTURE_ROOT / rel).read_bytes()
    d = gate.admit(rel, raw)
    assert d.admitted, f"{rel} deveria ser admitido, veio {d.verdict} ({d.reason})"
    assert d.content


@pytest.mark.parametrize("rel", MUST_REDACT)
def test_achado_isolado_redige_em_balanced(rel: str) -> None:
    """Em `balanced`, achado `high` isolado vira redação em vez de bloqueio."""
    g = SecurityGate(FIXTURE_ROOT, policy="balanced")
    raw = (FIXTURE_ROOT / rel).read_bytes()
    d = g.admit(rel, raw)
    assert d.verdict is Verdict.ALLOW_REDACTED, f"{rel}: {d.verdict} ({d.reason})"
    assert d.content is not None
    assert leaked(d.content) == []
    assert "RAGX:REDACTED" in d.content
    # redação preserva a contagem de linhas — senão start_line/end_line deslocam
    assert d.content.count("\n") == raw.decode().count("\n")


def test_deny_list_decide_sem_ler_bytes(gate: SecurityGate) -> None:
    for rel in (".env", "id_rsa", "private.pem", "credentials.json"):
        d = gate.admit(rel, raw=None)
        assert d.verdict is Verdict.BLOCK


def test_env_example_passa_fase1(gate: SecurityGate) -> None:
    assert gate.scanner.scan_filename(".env.example") is None


def test_placeholders_nao_geram_achado(gate: SecurityGate) -> None:
    content = (FIXTURE_ROOT / ".env.example").read_text()
    assert gate.scanner.scan_content(".env.example", content) == []


def test_alta_entropia_sem_semantica_de_segredo_e_permitida(gate: SecurityGate) -> None:
    rel = "tests/fixtures/sample.json"
    d = gate.admit(rel, (FIXTURE_ROOT / rel).read_bytes())
    assert d.admitted, f"{d.verdict} ({d.reason})"


def test_regra_de_alta_precisao_nao_e_rebaixada_por_contexto(gate: SecurityGate) -> None:
    """Um AKIA dentro de tests/ continua sendo BLOCK."""
    d = gate.admit("tests/fixtures/leak.py", b'KEY = "AKIAIOSFODNN7EXAMPLE"\n')
    assert d.verdict is Verdict.BLOCK


def test_gitignore_nao_e_politica_de_seguranca() -> None:
    """.env NÃO listado no .gitignore continua chegando ao scanner e sendo bloqueado."""
    g = SecurityGate(FIXTURE_ROOT)
    ignored, _ = g.ignore.should_ignore(".env")
    assert not ignored
    assert g.admit(".env", b"X=1").verdict is Verdict.BLOCK


# ── Relatório não pode vazar o que protege ──────────────────────────────
def test_findings_nao_carregam_o_valor(gate: SecurityGate) -> None:
    for rel, d in _admit_all(gate).items():
        for f in d.findings:
            blob = f"{f.rule_id}{f.digest}{f.preview}{f.path}"
            assert leaked(blob) == [], f"{rel}: finding vazou o valor"


def test_preview_de_valor_curto_nao_revela() -> None:
    from ragx.security.redactor import preview

    assert preview("abc123") == "«curto»"
    assert preview("A" * 40).count("…") == 1


def test_fixture_tem_todos_os_segredos_plantados() -> None:
    """A fixture precisa de fato conter cada segredo da lista — senão os testes
    acima passam por vacuidade."""
    blob = "\n".join(
        (FIXTURE_ROOT / rel).read_text(encoding="utf-8", errors="replace") for rel in _walk()
    )
    faltando = [s for s in SECRETS_UNDER_TEST if s not in blob]
    assert faltando == [], f"segredos não plantados na fixture: {faltando}"
