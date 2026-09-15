"""Fase 7 — Agent Knowledge Training (curadoria, NÃO fine-tuning)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.agents import evaluator, profile, trainer
from ragx.config import load_config
from ragx.core.errors import RagxError, UsageError
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios via SSO."""

    def login(self, c):
        """Valida o token e cria a sessao."""
        return self.sso.validate(c)
'''

PAY = '''class PaymentService:
    """Cobra o cliente."""

    def charge(self, o):
        """Envia a cobranca ao gateway."""
        return self.gateway.charge(o)
'''

NOTIFY = '''class NotificationService:
    """Envia notificacoes."""

    def send(self, m):
        """Publica na fila de mensagens."""
        return self.queue.publish(m)
'''

DOC = "# Autenticacao\n\n## Fluxo\n\nO AuthService valida o token no provedor.\n"


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(AUTH, encoding="utf-8")
    (tmp_path / "src" / "payment.py").write_text(PAY, encoding="utf-8")
    (tmp_path / "src" / "notify.py").write_text(NOTIFY, encoding="utf-8")
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    return tmp_path


# ── criação ─────────────────────────────────────────────────────────────
def test_cria_arvore_completa(proj: Path) -> None:
    r = profile.create(load_config(proj), "backend-architect")
    root = Path(r.path)
    assert (root / "manifest.json").is_file()
    assert (root / "rules" / "security.md").is_file()
    assert (root / "skills").is_dir() and (root / "evaluation" / "cases.yaml").is_file()


def test_manifest_valida_contra_o_schema(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "a1")
    manifest, _p = profile.load(cfg, "a1")
    assert manifest.schema_version == profile.SCHEMA and manifest.name == "a1"


def test_perfil_e_revisavel_em_pr(proj: Path) -> None:
    """Sem blob, sem binário: tudo texto."""
    r = profile.create(load_config(proj), "a2")
    for p in Path(r.path).rglob("*"):
        if p.is_file():
            assert p.suffix in (".md", ".json", ".yaml"), f"artefato binário: {p.name}"


def test_template_invalido(proj: Path) -> None:
    with pytest.raises(UsageError, match="template"):
        profile.create(load_config(proj), "a3", template="inexistente")


def test_perfil_duplicado(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "a4")
    with pytest.raises(UsageError, match="já existe"):
        profile.create(cfg, "a4")


@pytest.mark.parametrize("template", list(profile.TEMPLATES))
def test_todo_template_compila(proj: Path, template: str) -> None:
    cfg = load_config(proj)
    profile.create(cfg, f"t-{template}", template=template)
    r = trainer.train(cfg, f"t-{template}")
    assert r.rules >= 1 and r.tokens > 0


# ── treino ──────────────────────────────────────────────────────────────
def test_treina_e_preenche_o_manifest(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b1")
    trainer.train(cfg, "b1")
    manifest, paths = profile.load(cfg, "b1")
    assert manifest.knowledge.chunks > 0 and manifest.knowledge.dictionary_hash
    assert manifest.version == "2"
    assert paths.dictionary.is_file() and paths.instructions.is_file()


def test_security_md_e_obrigatorio(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b2")
    _m, paths = profile.load(cfg, "b2")
    (paths.rules / "security.md").unlink()
    with pytest.raises(RagxError, match=r"security\.md"):
        trainer.train(cfg, "b2")


def test_regra_curada_a_mao_e_preservada(proj: Path) -> None:
    """A garantia que mais importa no retreino."""
    cfg = load_config(proj)
    profile.create(cfg, "b3")
    _m, paths = profile.load(cfg, "b3")
    curada = paths.rules / "architecture.md"
    curada.write_text("# Minha regra\n\nEscrita à mão.\n", encoding="utf-8")

    trainer.train(cfg, "b3")
    trainer.train(cfg, "b3")

    assert curada.read_text(encoding="utf-8") == "# Minha regra\n\nEscrita à mão.\n"


def test_regra_gerada_fica_separada(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b4")
    trainer.train(cfg, "b4")
    _m, paths = profile.load(cfg, "b4")
    geradas = list(paths.rules.glob(f"*{profile.GENERATED_SUFFIX}"))
    if geradas:
        assert "gerado" in geradas[0].read_text(encoding="utf-8").lower()


def test_instructions_referencia_mcp_em_vez_de_despejar(proj: Path) -> None:
    """O perfil é um mapa, não um despejo de conhecimento."""
    cfg = load_config(proj)
    profile.create(cfg, "b5")
    trainer.train(cfg, "b5")
    _m, paths = profile.load(cfg, "b5")
    body = paths.instructions.read_text(encoding="utf-8")
    assert "get_dictionary" in body and "build_context" in body
    # a frase quebra em duas linhas no template; normaliza antes de procurar
    plano = " ".join(body.lower().split())
    assert "me explique o projeto" in plano
    assert "search_hybrid" in body and "get_chunk" in body


def test_instructions_cabe_no_orcamento(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b6")
    r = trainer.train(cfg, "b6", budget=6000)
    assert r.tokens <= 6000 and not r.warnings


def test_escopo_fora_da_raiz_e_recusado(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b7")
    manifest, paths = profile.load(cfg, "b7")
    manifest.scope.include_paths = ["../../etc/**"]
    paths.manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(RagxError, match="fora da raiz"):
        trainer.train(cfg, "b7")


def test_escopo_absoluto_e_recusado(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b8")
    manifest, paths = profile.load(cfg, "b8")
    manifest.scope.include_paths = ["/etc/**"]
    paths.manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(RagxError, match=r"fora da raiz|absoluto"):
        trainer.train(cfg, "b8")


def test_escopo_recorta_o_dicionario(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "b9", scope="src/auth.py")
    trainer.train(cfg, "b9")
    _m, paths = profile.load(cfg, "b9")
    data = json.loads(paths.dictionary.read_text(encoding="utf-8"))
    caminhos = {s["path"] for s in data["services"]}
    assert caminhos <= {"src/auth.py"}, f"escopo não recortou: {caminhos}"


def test_retreino_e_estavel(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "c1")
    trainer.train(cfg, "c1")
    _m, paths = profile.load(cfg, "c1")
    antes = paths.instructions.read_text(encoding="utf-8")
    trainer.train(cfg, "c1")
    assert paths.instructions.read_text(encoding="utf-8") == antes


def test_nenhum_segredo_no_perfil(proj: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fixtures.secrets_under_test import leaked

    cfg = load_config(proj)
    profile.create(cfg, "c2")
    trainer.train(cfg, "c2")
    _m, paths = profile.load(cfg, "c2")
    corpo = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in paths.root.rglob("*") if p.is_file()
    )
    assert leaked(corpo) == []


# ── avaliação ───────────────────────────────────────────────────────────
def test_eval_roda_e_reporta(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "d1")
    trainer.train(cfg, "d1")
    r = evaluator.evaluate(cfg, "d1")
    assert r.results and 0.0 <= r.recall_at_3 <= 1.0


def test_must_not_mention_reprova(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "d2")
    trainer.train(cfg, "d2")
    _m, paths = profile.load(cfg, "d2")
    (paths.evaluation / "cases.yaml").write_text(
        "- id: proibido\n"
        '  task: "autenticacao sso"\n'
        '  must_not_mention: ["AuthService"]\n',
        encoding="utf-8",
    )
    r = evaluator.evaluate(cfg, "d2")
    assert not r.results[0].passed
    assert any("proibido" in f for f in r.results[0].failures)


def test_resultado_e_versionado(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "d3")
    trainer.train(cfg, "d3")
    evaluator.evaluate(cfg, "d3")
    _m, paths = profile.load(cfg, "d3")
    assert (paths.evaluation / "results" / "latest.yaml").is_file()


def test_eval_e_reproduzivel(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "d4")
    trainer.train(cfg, "d4")
    a = evaluator.evaluate(cfg, "d4").recall_at_3
    b = evaluator.evaluate(cfg, "d4").recall_at_3
    assert a == b


def test_skill_inexistente_reprova(proj: Path) -> None:
    cfg = load_config(proj)
    profile.create(cfg, "d5")
    trainer.train(cfg, "d5")
    _m, paths = profile.load(cfg, "d5")
    (paths.evaluation / "cases.yaml").write_text(
        '- id: s1\n  task: "autenticacao"\n  expect_skill: "nao-existe"\n',
        encoding="utf-8",
    )
    r = evaluator.evaluate(cfg, "d5")
    assert not r.results[0].passed


def test_exemplo_proposto_precisa_de_promocao(proj: Path) -> None:
    """Exemplo ruim ensina padrão ruim: nada entra automaticamente."""
    cfg = load_config(proj)
    profile.create(cfg, "e1")
    _m, paths = profile.load(cfg, "e1")
    (paths.proposed / "abc123.md").write_text("# Exemplo\n", encoding="utf-8")

    assert not (paths.examples / "abc123.md").is_file()
    trainer.promote_example(cfg, "e1", "abc123")
    assert (paths.examples / "abc123.md").is_file()
    assert not (paths.proposed / "abc123.md").is_file()


def test_perfil_inexistente(proj: Path) -> None:
    with pytest.raises(UsageError, match="não encontrado"):
        profile.load(load_config(proj), "fantasma")
