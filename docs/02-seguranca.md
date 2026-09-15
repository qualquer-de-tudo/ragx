# 02 — Segurança (Fase 0)

> Este é o documento que não admite atalho. Se algo aqui não estiver funcionando,
> **nenhuma outra fase pode começar**.

## Modelo de ameaça

| # | Ameaça | Vetor | Mitigação |
|---|--------|-------|-----------|
| A1 | Segredo indexado como chunk | `.env`, `credentials.json` lidos pelo walker | Deny-list de nomes no `SecurityScanner` |
| A2 | Segredo dentro de arquivo legítimo | `config.yaml` com `API_KEY: sk-live-...` | Scanner de conteúdo (regex + entropia) + redação |
| A3 | Segredo vazado para provedor de embedding | Chunk enviado para Ollama/API remota | Gate roda **antes** do embedder; sem exceção |
| A4 | Segredo no grafo | Entidade nomeada a partir de um valor secreto | Extratores só consomem chunks já admitidos |
| A5 | Segredo servido a um agente | Ferramenta MCP devolve trecho sensível | MCP lê apenas do store; store não contém segredo |
| A6 | Segredo exportado no `.rag` | Pacote compartilhado com o time | Re-scan obrigatório no export |
| A7 | Segredo no próprio relatório de segurança | Log com o valor detectado | `Redactor`: guarda-se `sha256` + máscara, nunca o valor |
| A8 | Path traversal / symlink para fora do projeto | `link -> /home/user/.ssh` | Walker recusa symlink que escapa da raiz |
| A9 | Segredo reintroduzido após índice antigo | Arquivo já indexado vira sensível | Re-scan no `sync`; chunks órfãos são purgados |

Fora do escopo do MVP: proteção contra usuário local malicioso com acesso de escrita
ao `ragx.toml` (ele pode desligar regras). Mitigação parcial: `ragx security scan`
sempre reporta regras desabilitadas, e o export falha se o *ruleset* estiver enfraquecido.

## Componentes

```text
                 caminho do arquivo
                         │
                         ▼
              ┌──────────────────────┐
              │    IgnoreEngine      │  .gitignore .dockerignore .ragignore + defaults
              └──────────┬───────────┘
                    SKIP │ ALLOW
                         ▼
              ┌──────────────────────┐
              │  SecurityScanner     │  ── fase 1: nome do arquivo (deny-list)
              │                      │  ── fase 2: conteúdo (regex + entropia)
              └──────────┬───────────┘
              BLOCK │    │ ALLOW / ALLOW_REDACTED
                    ▼    ▼
          SecurityEvent  conteúdo (possivelmente redigido)
          (hash + máscara)          │
                                    ▼
                                 Parser
```

### `SecurityGate` — a fachada

```python
class Verdict(StrEnum):
    ALLOW = "allow"                    # segue para o parser
    ALLOW_REDACTED = "allow_redacted"  # segue, com segredos substituídos por placeholder
    SKIP = "skip"                      # ignorado por .gitignore/.ragignore — não é incidente
    BLOCK = "block"                    # bloqueado por política de segurança — é incidente

@dataclass(frozen=True)
class GateDecision:
    verdict: Verdict
    path: Path
    rule_id: str | None
    findings: tuple[SecurityFinding, ...]
    content: str | None      # None em SKIP/BLOCK
```

A API pública é uma só:

```python
gate.admit(path: Path, raw: bytes) -> GateDecision
```

Nenhum componente fora de `security/` pode ler `raw` sem passar por `admit()`.

## IgnoreEngine

Lê, na ordem de precedência (o último vence):

```text
1. defaults embutidos do RAGX
2. .gitignore      (todos, inclusive aninhados)
3. .dockerignore
4. .ragignore      (específico do RAGX)
5. ragx.toml -> [index].exclude
6. flags da CLI    (--exclude)
```

Implementação: `pathspec` com `GitWildMatchPattern`, respeitando negação (`!pattern`),
padrões aninhados por diretório e `.gitignore` global do usuário (opt-in em config).

Defaults embutidos (resumo — lista completa em `security/rules/default_ignore.txt`):

```text
.git/  .svn/  .hg/
node_modules/  vendor/  .venv/  venv/  __pycache__/
dist/  build/  target/  .next/  .nuxt/
*.min.js  *.map  *.lock  package-lock.json  poetry.lock  uv.lock
*.png *.jpg *.jpeg *.gif *.ico *.svg *.webp *.pdf
*.zip *.tar *.gz *.7z *.rar
*.exe *.dll *.so *.dylib *.class *.jar *.pyc
*.db *.sqlite *.sqlite3
.ragx/
```

**Importante:** `.gitignore` é heurística de *ruído*, não de *segurança*. Um `.env`
não listado no `.gitignore` continua sendo bloqueado pelo scanner. O IgnoreEngine
reduz volume; quem protege é o scanner.

## SecurityScanner — fase 1: nome do arquivo

Deny-list por *glob*, avaliada antes de qualquer leitura de conteúdo.
Arquivo que casa é **bloqueado**: 0 bytes vão adiante.

```text
.env  .env.*  *.env
*.pem  *.key  *.p12  *.pfx  *.jks  *.keystore
id_rsa  id_dsa  id_ecdsa  id_ed25519   (e variações sem extensão)
*.ppk
credentials*  *credential*
secret*  *secrets*
token*  *tokens*
password*  *passwd*
.htpasswd  .netrc  .pgpass  .my.cnf
*.kdbx
service-account*.json   gcp-*.json   aws-credentials*
.aws/*  .ssh/*  .gnupg/*  .docker/config.json
*.tfstate  *.tfstate.backup      # state do Terraform carrega segredo em claro
```

Exceções explícitas (permitidas, porque são *templates* sem valor real):

```text
.env.example  .env.sample  .env.template  .env.dist
credentials.example*  secrets.example*
*.pem.example
```

Mesmo nas exceções o conteúdo passa pela fase 2 — template com segredo real vira `BLOCK`.

## SecurityScanner — fase 2: conteúdo

Três detectores combinados, todos declarados em YAML (`security/rules/*.yaml`) para
serem auditáveis e testáveis sem mexer em código:

```yaml
- id: aws-access-key-id
  severity: critical
  pattern: '\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b'
  action: block

- id: generic-api-key-assignment
  severity: high
  pattern: '(?i)\b(api[_-]?key|apikey|secret|token|passwd|password|access[_-]?key)\b\s*[:=]\s*["'']?([^\s"'']{12,})'
  capture_group: 2
  action: redact
  min_entropy: 3.0
  allow_placeholders: true
```

### 1. Regras de padrão (alta precisão)

Provedores com formato reconhecível — bloqueio direto, sem heurística:

```text
AWS access key / secret       GitHub PAT (ghp_, gho_, ghs_, github_pat_)
Google API key (AIza...)      Slack token (xox[baprs]-)
Stripe (sk_live_, rk_live_)   OpenAI / Anthropic (sk-, sk-ant-)
JWT (eyJ...eyJ...)            PEM blocks (-----BEGIN ... PRIVATE KEY-----)
Azure connection string       Twilio (SK..., AC...)
SendGrid (SG.)                npm token (npm_)
Postgres/MySQL/Mongo URI com senha embutida
```

### 2. Atribuição + entropia (recall)

Detecta `CHAVE = valor` onde a chave sugere segredo **e** o valor tem entropia de
Shannon alta o bastante.

```text
entropia(valor) >= 3.0 bits/char   e   len(valor) >= 12
        e não casa com allowlist de placeholder
```

Allowlist de placeholder (evita falso positivo):

```text
changeme  change_me  your-api-key  <your_key>  xxx...  ***  REDACTED
example  sample  dummy  placeholder  foo  bar  test  localhost
${...}  {{...}}  %env(...)%   os.environ[...]   process.env.*
```

### 3. Contexto de arquivo

Multiplicadores de severidade por tipo de arquivo — um valor de alta entropia em
`docker-compose.yml` é mais suspeito do que em `fixtures/data.json`.

```text
docker-compose*.yml  *.tfvars  *.ini  *.cfg  *.properties   → severidade +1
**/test/**  **/tests/**  **/fixtures/**  **/*_test.*        → severidade -1 (nunca abaixo de "medium")
```

Redução de severidade **nunca** cancela uma regra de padrão de alta precisão:
um `AKIA...` dentro de `tests/` continua sendo `BLOCK`.

## Ações

| Ação | Efeito | Quando |
|------|--------|--------|
| `block` | Arquivo inteiro descartado. `SecurityEvent` gravado. | Regra de padrão, deny-list de nome, ou >= N achados |
| `redact` | Valor trocado por `«RAGX:REDACTED:<rule_id>»` antes do chunking | Achado isolado em arquivo com conteúdo legítimo |
| `warn` | Indexa normalmente, registra evento | Baixa confiança, `--strict` desligado |

Política padrão (`security.policy = "strict"`): qualquer achado `critical`/`high`
promove o arquivo inteiro para `block`. Em `"balanced"`, `high` isolado vira `redact`.
`"permissive"` não existe — deliberadamente.

## Redactor

O valor do segredo **nunca** é persistido, logado ou impresso. O que se guarda:

```python
@dataclass(frozen=True)
class SecurityFinding:
    rule_id: str
    severity: Severity
    path: str
    line: int
    column: int
    digest: str      # sha256(valor)[:16] — permite deduplicar sem revelar
    preview: str     # "sk-a…5f2c" — 4 primeiros + 4 últimos, resto mascarado
```

Regra: `preview` só é gerado se `len(valor) >= 16`; abaixo disso, `"«curto»"`.

## CLI da Fase 0

```bash
ragx init                      # cria .ragx/, ragx.toml, .ragignore
ragx doctor                    # valida ambiente: python, sqlite+FTS5, embedder, regras
ragx security scan .           # varre sem indexar
ragx security scan . --json    # saída para CI
ragx security rules            # lista regras ativas e desabilitadas
```

Saída esperada de `ragx security scan .`:

```text
Security scan — /projeto

  BLOCKED (7)
    .env                            filename-deny:dotenv
    .env.production                 filename-deny:dotenv
    credentials.json                filename-deny:credentials
    id_rsa                          filename-deny:ssh-private-key
    private.pem                     filename-deny:pem
    config.yaml                     content:generic-api-key-assignment (L12)
    docker-compose.yml              content:password-assignment (L31)

  REDACTED (2)
    src/settings.py                 1 achado
    infra/terraform/main.tf         1 achado

  SKIPPED (43)   por .gitignore/.ragignore

Ruleset: builtin@1 (48 regras, 0 desabilitadas)   Política: strict
Exit code: 1 (achados críticos presentes)
```

Exit codes: `0` limpo · `1` achados bloqueantes · `2` erro de execução.

## Critério de aceite da Fase 0

Fixture `tests/fixtures/secret_project/` contendo:

```text
.env
.env.production
credentials.json
id_rsa
private.pem
config.yaml              # com API_KEY real-looking
docker-compose.yml       # com POSTGRES_PASSWORD
.env.example             # placeholder — deve ser PERMITIDO
tests/fixtures/fake.json # valor alto-entropia — deve ser permitido/warn
```

Depois de `ragx index .` sobre essa fixture, esta consulta precisa devolver zero
em **todas** as superfícies:

```text
chunks contendo o segredo         → 0
embeddings gerados do segredo     → 0
nós de grafo derivados do segredo → 0
resultados MCP com o segredo      → 0
bytes do segredo no .rag exportado→ 0
```

O teste é escrito na Fase 0 com os alvos das fases futuras marcados `xfail`,
e cada fase posterior tem como *definition of done* virar seu `xfail` em `pass`.

**Não avançar para a Fase 1 enquanto isso não estiver verde.**
