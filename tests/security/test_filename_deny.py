"""Fase 1 do gate: o que o NOME do arquivo decide — e o que ele não decide.

Esta suíte existe por causa de um bug específico e caro: a regra
`filename-deny:tokens` casava `**/tokens.*` e bloqueava `src/ragx/tokens.py`
— o módulo de contagem de tokens do próprio RAGX. O RAGX não conseguia se
indexar. O mesmo acontecia com `tokens.ts` (design tokens), `docs/tokens.md`
e qualquer `auth_token.go` de qualquer projeto.

A correção NÃO foi abrir exceção para arquivo sensível. Foi separar duas
coisas que a deny-list confundia:

- regras de FORMATO ou LOCAL (`*.pem`, `.ssh/**`, `.env`) — o arquivo é, por
  definição, um recipiente de segredo. Continuam absolutas.
- regras que ADIVINHAM pelo nome (`tokens`, `secrets`, `password`) — num
  arquivo de código-fonte elas erram mais do que acertam. Esses arquivos
  seguem para a fase 2, que lê o conteúdo inteiro.

Por isso os dois lados são testados aqui juntos: quem afrouxar a fase 1 sem
manter a fase 2 quebra `test_segredo_real_em_arquivo_de_codigo_ainda_bloqueia`.
"""

from __future__ import annotations

import pytest

from ragx.core.models import Verdict
from ragx.security.gate import SecurityGate
from ragx.security.scanner import Ruleset

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def gate(tmp_path_factory) -> SecurityGate:
    return SecurityGate(tmp_path_factory.mktemp("projeto"))


# ── o bug original ──────────────────────────────────────────────────────
def test_o_ragx_consegue_indexar_o_proprio_tokens_py(gate: SecurityGate) -> None:
    """A regressão que dá nome a este arquivo."""
    d = gate.admit("src/ragx/tokens.py")
    assert d.verdict is Verdict.ALLOW, (
        f"src/ragx/tokens.py bloqueado por {d.rule_id!r}. É o módulo de contagem "
        f"de tokens do RAGX — se ele não entra no índice, o RAGX não indexa a si mesmo."
    )


@pytest.mark.parametrize(
    "caminho",
    [
        "src/ragx/tokens.py",          # o caso original
        "src/design/tokens.ts",        # design tokens — comum em todo front-end
        "src/design/tokens.scss",
        "docs/tokens.md",              # documentação SOBRE tokens
        "app/auth_token.py",           # `**/*_token*`
        "pkg/refresh-token.go",        # `**/*-token*`
        "src/secrets.py",              # módulo que LÊ segredos, não os contém
        "internal/credentials.java",
        "lib/password.rs",
        "web/passwordField.tsx",
    ],
)
def test_codigo_fonte_com_nome_sugestivo_nao_e_bloqueado_pelo_nome(
    gate: SecurityGate, caminho: str
) -> None:
    d = gate.admit(caminho)
    assert d.verdict is Verdict.ALLOW, f"{caminho} bloqueado por {d.rule_id!r}"


# ── a proteção continua de pé ───────────────────────────────────────────
@pytest.mark.parametrize(
    ("caminho", "regra"),
    [
        (".env", "dotenv"),
        (".env.production", "dotenv"),
        ("config/.env.local", "dotenv"),
        ("private.pem", "pem"),
        ("cert.p12", "pem"),
        ("server.key", "private-key"),
        ("id_rsa", "ssh-private-key"),
        (".ssh/id_ed25519", "ssh-private-key"),
        ("credentials.json", "credentials"),
        (".aws/credentials", "credentials"),
        ("secrets.yaml", "secrets"),
        ("secrets.yml", "secrets"),
        ("tokens.json", "tokens"),
        ("config/tokens.toml", "tokens"),
        ("api_token.txt", "tokens"),
        ("password.txt", "password-file"),
        (".htpasswd", "password-file"),
        (".netrc", "shell-credentials"),
        (".pgpass", "shell-credentials"),
        ("service-account-prod.json", "cloud-credentials"),
        ("vault.kdbx", "password-manager"),
        ("terraform.tfstate", "terraform-state"),
        ("prod.tfvars", "terraform-state"),
    ],
)
def test_arquivo_sensivel_continua_bloqueado_pelo_nome(
    gate: SecurityGate, caminho: str, regra: str
) -> None:
    d = gate.admit(caminho)
    assert d.verdict is Verdict.BLOCK, f"{caminho} passou — deveria ser bloqueado"
    assert d.rule_id == f"filename-deny:{regra}"


def test_formato_de_dados_nao_ganha_a_liberacao_de_codigo(gate: SecurityGate) -> None:
    """`.json`, `.yaml` e `.toml` ficam de fora de propósito: é onde credencial
    de verdade mora. Se alguém os adicionar a `code_extensions`, isto quebra."""
    rules = Ruleset()
    proibidas = {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".xml", ".txt", ".csv"}
    vazando = proibidas & rules.code_extensions
    assert not vazando, (
        f"formato de dados em code_extensions: {sorted(vazando)}. "
        f"`credentials.json` e `secrets.yaml` voltariam a passar pelo nome."
    )


# ── a fase 2 é quem segura o risco que a fase 1 soltou ──────────────────
def test_segredo_real_em_arquivo_de_codigo_ainda_bloqueia(gate: SecurityGate) -> None:
    """O contrapeso da correção.

    `tokens.py` passa pelo NOME. Se tiver uma credencial de verdade dentro,
    o conteúdo o bloqueia assim mesmo. Sem isto, a correção do falso positivo
    teria aberto um buraco real.
    """
    conteudo = b'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
    d = gate.admit("src/ragx/tokens.py", conteudo)
    assert d.verdict is Verdict.BLOCK, (
        "um segredo dentro de um arquivo .py liberado na fase 1 precisa ser "
        "pego na fase 2 — é esse o acordo que torna a liberação segura"
    )
    assert d.content is None


def test_codigo_legitimo_com_a_palavra_token_passa_com_conteudo(gate: SecurityGate) -> None:
    conteudo = (
        b"def count_tokens(text: str) -> int:\n"
        b'    """Conta tokens com tiktoken."""\n'
        b"    return len(text.split())\n"
    )
    d = gate.admit("src/ragx/tokens.py", conteudo)
    assert d.verdict is Verdict.ALLOW
    assert d.content is not None and "count_tokens" in d.content


# ── invariantes da regra ────────────────────────────────────────────────
def test_apenas_regras_de_palpite_sao_afrouxadas() -> None:
    """Uma regra de FORMATO nunca pode virar `content_decides`.

    Marcar `pem` ou `ssh-private-key` assim faria `chave.pem` depender de o
    scanner reconhecer o corpo da chave — e uma chave em formato novo passaria.
    """
    rules = Ruleset()
    absolutas = {
        "dotenv", "pem", "private-key", "ssh-private-key", "shell-credentials",
        "cloud-credentials", "password-manager", "terraform-state",
    }
    erradas = [r.id for r in rules.filename_rules if r.content_decides and r.id in absolutas]
    assert not erradas, (
        f"regras de formato/local marcadas como content_decides: {erradas}. "
        f"Elas descrevem o que o arquivo É, não um palpite sobre o nome."
    )


def test_nenhuma_extensao_de_codigo_esta_vazia_ou_sem_ponto() -> None:
    rules = Ruleset()
    assert rules.code_extensions, "a lista sumiu — todo código voltaria a ser bloqueado pelo nome"
    ruins = [e for e in rules.code_extensions if not e.startswith(".") or e != e.lower()]
    assert not ruins, f"extensões malformadas: {ruins} (o sufixo comparado vem de Path.suffix)"
