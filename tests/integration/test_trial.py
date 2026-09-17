"""`ragx trial` — a economia estimada, e a honestidade dela.

O risco desta feature não é errar a conta: é a conta certa virar promessa
errada. "O RAGX economiza 87% dos seus tokens" é uma frase que sobrevive à
ressalva que a acompanhava, e passa a ser citada sozinha.

Por isso metade desta suíte testa NÚMEROS e a outra metade testa que o número
sai acompanhado do que ele significa — e que ele não conta o que não deveria.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.trial import RESSALVA, run
from ragx.trial import _contar_arquivos as contar

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios via SSO corporativo."""

    def login(self, credentials):
        """Valida o token e cria a sessao no Redis."""
        return self.sso.validate(credentials)
'''


@pytest.fixture()
def projeto(tmp_path: Path):
    from ragx.indexing.pipeline import index_project

    raiz = tmp_path / "p"
    (raiz / "src").mkdir(parents=True)
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (raiz / "src" / "auth.py").write_text(AUTH, encoding="utf-8")
    (raiz / "README.md").write_text(
        "# Demo\n\nAutenticacao via SSO. O AuthService valida o token.\n", encoding="utf-8"
    )
    cfg = load_config(raiz)
    index_project(cfg)
    return cfg


# ── a ressalva ──────────────────────────────────────────────────────────
def test_o_resultado_carrega_a_ressalva(projeto) -> None:
    d = run(projeto, "autenticacao", tokens=1000).to_dict()
    assert d["is_estimate"] is True
    assert d["disclaimer"] == RESSALVA


def test_a_ressalva_diz_que_nao_e_consumo_real() -> None:
    texto = RESSALVA.lower()
    assert "estimativa" in texto
    assert "não" in texto and "real" in texto
    assert "fatura" in texto, "quem lê precisa saber que isto não prevê custo"


def test_os_campos_se_chamam_estimated(projeto) -> None:
    """Nome de campo é documentação que ninguém pula."""
    d = run(projeto, "autenticacao", tokens=1000).to_dict()
    assert "estimated_tokens" in d["context"]
    assert "estimated_tokens" in d["baseline_full_read"]
    assert "estimated_savings" in d
    assert "saved_tokens" not in d, "sem campo que soe a economia consumada"


def test_o_contador_de_tokens_usado_e_declarado(projeto) -> None:
    # Sem isso, dois números medidos com contadores diferentes parecem
    # comparáveis entre si.
    d = run(projeto, "autenticacao", tokens=1000).to_dict()
    assert d["token_counter"]


# ── a conta ─────────────────────────────────────────────────────────────
def test_os_dois_lados_usam_o_mesmo_contador(projeto) -> None:
    """Contar o contexto com um tokenizador e o basal com outro produziria
    uma razão sem sentido — e favorável ao RAGX por acidente."""
    r = run(projeto, "autenticacao", tokens=1000)
    from ragx.tokens import get_counter

    assert r.counter == get_counter().name


def test_a_economia_e_diferenca_e_razao_coerentes(projeto) -> None:
    r = run(projeto, "autenticacao", tokens=1000)
    assert r.saved_tokens == r.baseline.tokens - r.context_tokens
    if r.baseline.tokens > 0:
        assert r.saved_ratio == pytest.approx(r.saved_tokens / r.baseline.tokens)
        assert -1.0 <= r.saved_ratio <= 1.0


def test_basal_vazio_nao_vira_zero_por_cento(projeto) -> None:
    """`None` diz "não houve o que comparar"; `0.0` afirmaria "não poupou nada"."""
    r = run(projeto, "pergunta que nao casa com nada", tokens=1000, paths=[])
    if r.baseline.tokens == 0:
        assert r.saved_ratio is None
        assert r.to_dict()["estimated_savings"]["comparable"] is False


def test_economia_negativa_e_reportada_como_negativa(projeto) -> None:
    """Contexto maior que o basal existe: um arquivo minúsculo com orçamento
    grande. Arredondar isso para zero esconderia o caso em que o RAGX não
    ajuda."""
    pequeno = Path(projeto.root) / "min.py"
    pequeno.write_text("x = 1\n", encoding="utf-8")
    r = run(projeto, "autenticacao", tokens=3000, paths=["min.py"])
    if r.context_tokens > r.baseline.tokens:
        assert r.saved_tokens < 0
        assert r.saved_ratio is not None and r.saved_ratio < 0


# ── casos extremos ──────────────────────────────────────────────────────
def test_arquivo_vazio_conta_como_lido_com_zero_tokens(projeto) -> None:
    (Path(projeto.root) / "vazio.py").write_text("", encoding="utf-8")
    b = contar(projeto, ["vazio.py"])
    assert b.empty_files == 1
    assert b.files == 1, "foi lido — só não tinha conteúdo"
    assert b.tokens == 0


def test_arquivo_binario_nao_entra_no_basal(projeto) -> None:
    (Path(projeto.root) / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00binario")
    b = contar(projeto, ["logo.png"])
    assert b.tokens == 0
    assert b.files == 0
    assert sum(b.excluded.values()) >= 1, "precisa aparecer como excluído, não sumir"


def test_arquivo_gigante_e_excluido_e_nao_truncado(projeto) -> None:
    """Truncar inventaria um número. Excluir subestima — o lado seguro."""
    grande = Path(projeto.root) / "grande.py"
    grande.write_text("# " + "a" * (projeto.index.max_file_bytes + 1000), encoding="utf-8")
    b = contar(projeto, ["grande.py"])
    assert b.files == 0
    assert b.tokens == 0
    assert sum(b.excluded.values()) >= 1


def test_utf8_com_acento_e_contado(projeto) -> None:
    alvo = Path(projeto.root) / "acentos.py"
    alvo.write_text('# configuração de autenticação\nx = "ação"\n', encoding="utf-8")
    b = contar(projeto, ["acentos.py"])
    assert b.files == 1
    assert b.tokens > 0


def test_multiplos_arquivos_somam(projeto) -> None:
    b1 = contar(projeto, ["src/auth.py"])
    b2 = contar(projeto, ["README.md"])
    juntos = contar(projeto, ["src/auth.py", "README.md"])
    assert juntos.files == 2
    assert juntos.tokens == b1.tokens + b2.tokens


def test_caminho_inexistente_e_reportado(projeto) -> None:
    b = contar(projeto, ["nao/existe.py"])
    assert b.files == 0
    assert b.excluded.get("not_found") == 1


# ── segurança: o basal não pode contar o que não se pode ler ────────────
def test_env_nao_entra_no_basal(projeto) -> None:
    """Contar o `.env` inflaria a economia com tokens que o RAGX jamais
    serviria — e exigiria LER o segredo para contá-lo."""
    (Path(projeto.root) / ".env").write_text(
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n", encoding="utf-8"
    )
    b = contar(projeto, [".env"])
    assert b.files == 0
    assert b.tokens == 0
    assert b.excluded.get("blocked_by_security_gate") == 1


@pytest.mark.parametrize("nome", ["id_rsa", "private.pem", "credentials.json", "secrets.yaml"])
def test_arquivo_sensivel_nao_entra_no_basal(projeto, nome: str) -> None:
    (Path(projeto.root) / nome).write_text("conteudo sensivel\n", encoding="utf-8")
    b = contar(projeto, [nome])
    assert b.files == 0
    assert b.excluded.get("blocked_by_security_gate") == 1


def test_gitignore_tira_do_basal(projeto) -> None:
    raiz = Path(projeto.root)
    (raiz / ".gitignore").write_text("ignorado.py\n", encoding="utf-8")
    (raiz / "ignorado.py").write_text("x = 1\n" * 200, encoding="utf-8")

    b = contar(projeto, ["ignorado.py"])
    assert b.files == 0, "o RAGX não indexaria; contar no basal inflaria a economia"


def test_dockerignore_tira_do_basal(projeto) -> None:
    raiz = Path(projeto.root)
    (raiz / ".dockerignore").write_text("build/\n", encoding="utf-8")
    (raiz / "build").mkdir()
    (raiz / "build" / "saida.js").write_text("var x = 1;\n" * 200, encoding="utf-8")

    b = contar(projeto, ["build/saida.js"])
    assert b.files == 0


def test_o_projeto_inteiro_nunca_inclui_segredo(projeto) -> None:
    """O caso que importa: `--scope project` varre tudo."""
    (Path(projeto.root) / ".env").write_text("TOKEN=abc123xyz\n", encoding="utf-8")
    b = contar(projeto, None)
    assert b.excluded.get("blocked_by_security_gate", 0) >= 1
    assert b.files > 0, "o resto do projeto continua sendo contado"


# ── escopos ─────────────────────────────────────────────────────────────
def test_escopo_project_e_maior_ou_igual_a_sources(projeto) -> None:
    fontes = run(projeto, "autenticacao", tokens=1000, scope="sources")
    tudo = run(projeto, "autenticacao", tokens=1000, scope="project")
    assert tudo.baseline.tokens >= fontes.baseline.tokens


def test_escopo_aparece_no_resultado(projeto) -> None:
    # Sem o escopo, dois números incomparáveis parecem comparáveis.
    assert run(projeto, "x", tokens=1000, scope="project").to_dict()["scope"] == "project"
    assert run(projeto, "x", tokens=1000, paths=["README.md"]).to_dict()["scope"] == "paths"


def test_glob_nao_escapa_da_raiz(projeto) -> None:
    """Glob é FILTRO sobre o que o walker emitiu, nunca varredura do disco.

    Por isso `--path` não é uma porta para fora da raiz nem para dentro do que
    o Security Gate bloqueia: o walker não emite nenhum dos dois.
    """
    from ragx.trial import matches

    assert not matches("src/auth.py", ["../../*.py"])
    assert matches("src/auth.py", ["**/*.py"])
    assert matches("src/auth.py", ["*.py"]), "padrão sem diretório casa o basename"

    fora = run(projeto, "autenticacao", tokens=1000, globs=["../../*"])
    assert fora.baseline.files == 0


def test_glob_nao_alcanca_arquivo_bloqueado(projeto) -> None:
    (Path(projeto.root) / ".env").write_text("TOKEN=abc123\n", encoding="utf-8")
    r = run(projeto, "autenticacao", tokens=1000, globs=["*"])
    assert r.baseline.excluded.get("blocked_by_security_gate", 0) >= 1
    assert r.baseline.tokens > 0, "o resto continua contado"
