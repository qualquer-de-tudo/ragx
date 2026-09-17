"""Camada do documento: conhecimento, registro de trabalho ou teste.

`task/` é 22% dos chunks deste repositório — mais que toda a documentação — e
vencia o código na busca. Para *"como o security gate decide bloquear um
arquivo"*, o primeiro fragmento era o enunciado da TAREFA que pediu para
construir o gate, não o código que o implementa.

O que estes testes protegem não é só a classificação: é a decisão de **pesar e
não excluir**. Um `task/` invisível seria pior que um `task/` ruidoso — às
vezes a resposta está mesmo na tarefa.

Ver `task/fase-14-evolucao-do-rag/RAGX-0102-*.md`.
"""

from __future__ import annotations

import pytest

from ragx.tiers import DEFAULT_TEST, DEFAULT_WORK, Tier, classify, weight_for

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("caminho", "esperado"),
    [
        ("src/ragx/security/gate.py", Tier.KNOWLEDGE),
        ("docs/02-seguranca.md", Tier.KNOWLEDGE),
        ("README.md", Tier.KNOWLEDGE),
        ("@base/agents/engineering/security.md", Tier.KNOWLEDGE),
        ("task/fase-00-fundacao/RAGX-0005-scanner.md", Tier.WORK),
        ("tasks/algo.md", Tier.WORK),
        ("backlog/ideia.md", Tier.WORK),
        ("tests/unit/test_x.py", Tier.TEST),
        ("spec/algo_spec.rb", Tier.TEST),
        ("__tests__/App.test.tsx", Tier.TEST),
    ],
)
def test_classificacao_por_caminho(caminho: str, esperado: Tier) -> None:
    assert classify(caminho) is esperado


def test_conhecimento_e_o_default() -> None:
    """Um caminho que não casa com nada é conhecimento — nunca o contrário.

    O default oposto esconderia silenciosamente arquivos legítimos de qualquer
    projeto com uma estrutura que os padrões não previram.
    """
    assert classify("qualquer/coisa/nova.py") is Tier.KNOWLEDGE


def test_work_vence_test_quando_os_dois_casam() -> None:
    """`task/tests-do-plano.md` é plano, não teste."""
    assert classify("task/tests-do-plano.md") is Tier.WORK


def test_separador_do_windows_e_normalizado() -> None:
    assert classify("task\\fase-00\\RAGX-0001.md") is Tier.WORK


def test_padroes_configurados_substituem_o_default() -> None:
    assert classify("adr-drafts/x.md", work=("adr-drafts/",)) is Tier.WORK
    # E com a configuração explícita, o default deixa de valer.
    assert classify("task/x.md", work=("adr-drafts/",)) is Tier.KNOWLEDGE


def test_lista_vazia_desliga_a_classificacao() -> None:
    """Quem não quiser o mecanismo desliga com uma lista vazia, sem gambiarra."""
    assert classify("task/x.md", work=(), test=()) is Tier.KNOWLEDGE


def test_defaults_sao_conservadores() -> None:
    """Default que classifica demais esconde conhecimento legítimo sem avisar."""
    for padrao in DEFAULT_WORK + DEFAULT_TEST:
        assert padrao.endswith("/"), (
            f"{padrao!r} casa arquivo solto, não diretório — perigoso demais "
            f"para um default"
        )
    assert "src/" not in DEFAULT_WORK + DEFAULT_TEST
    assert "docs/" not in DEFAULT_WORK + DEFAULT_TEST


# ── o peso ──────────────────────────────────────────────────────────────
def test_conhecimento_e_a_referencia() -> None:
    """`knowledge` é sempre 1,0: mexer nele deslocaria a escala sem mudar ordem."""
    assert weight_for(Tier.KNOWLEDGE, work_weight=0.1, test_weight=0.1) == 1.0


def test_o_peso_reduz_sem_zerar() -> None:
    assert 0.0 < weight_for(Tier.WORK, 0.45, 0.7) < 1.0
    assert 0.0 < weight_for(Tier.TEST, 0.45, 0.7) < 1.0


def test_peso_neutro_preserva_o_comportamento_antigo() -> None:
    for tier in Tier:
        assert weight_for(tier, 1.0, 1.0) == 1.0


def test_a_tarefa_ainda_pode_ser_encontrada(tmp_path) -> None:
    """Pesar e não excluir: uma consulta cuja resposta ESTÁ na tarefa a acha.

    É o contrapeso da correção. Se o peso virasse exclusão, este teste quebra.
    """
    from ragx.config import load_config
    from ragx.indexing.pipeline import index_project
    from ragx.search.service import search

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "task").mkdir()
    (tmp_path / "task" / "plano.md").write_text(
        "# Plano de migracao do Zorbnak\n\n"
        "O Zorbnak sera migrado em tres etapas, comecando pelo modulo de faturamento.\n",
        encoding="utf-8",
    )
    (tmp_path / "src.py").write_text("def nada():\n    return 1\n", encoding="utf-8")

    cfg = load_config(tmp_path)
    index_project(cfg)

    res = search(cfg, "Zorbnak migracao etapas", mode="keyword", limit=5).results
    assert any("task/plano.md" in r.document_path for r in res), (
        "a tarefa sumiu do resultado — o peso virou exclusão"
    )
