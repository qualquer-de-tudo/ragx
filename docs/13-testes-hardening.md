# 13 — Testes e Hardening (Fase 10)

## Pirâmide

```text
        e2e/          poucos, lentos, cobrem o caminho real
      integration/    SQLite real, fixtures reais
    unit/             maioria, rápidos, sem I/O
  security/           ── categoria própria, bloqueante, roda sempre
```

`security/` não é uma camada da pirâmide: é um **portão**. Falhou, nada é liberado.

| Suíte | Alvo | Runtime alvo |
|-------|------|--------------|
| `unit/` | chunkers, IDs, fusion, budget, entropia, regras | < 10 s |
| `integration/` | pipeline de indexação, repositórios, FTS5, grafo | < 60 s |
| `security/` | gate, fixture de segredos, 5 superfícies, testes arquiteturais | < 30 s |
| `e2e/` | `init → index → search → context → mcp → export → import` | < 5 min |
| `eval/` | qualidade de recuperação (não bloqueia build, reporta métrica) | — |

Cobertura mínima: **90% em `src/ragx/security/`** e **80% no restante**.
Cobertura de `security/` é gate de CI; a geral é aviso.

## A fixture de segredos

`tests/fixtures/secret_project/` — um projeto falso, completo, com segredos falsos
plantados. É o artefato de teste mais importante do repositório.

```text
tests/fixtures/secret_project/
├── .gitignore
├── .dockerignore
├── .ragignore
├── .env                        AWS_SECRET_ACCESS_KEY, DB_PASSWORD
├── .env.production             STRIPE_SECRET_KEY
├── .env.example                placeholders — DEVE ser indexado
├── credentials.json            service account falso
├── id_rsa                      chave privada falsa
├── private.pem                 PEM falso
├── docker-compose.yml          POSTGRES_PASSWORD embutido
├── config.yaml                 API_KEY embutido
├── src/
│   ├── app.py                  código legítimo — DEVE ser indexado
│   └── settings.py             uma linha com token → redact
├── docs/
│   └── setup.md                menciona "API_KEY" sem valor — DEVE ser indexado
└── tests/
    └── fixtures/sample.json    alto entropia, sem semântica de segredo → permitido
```

Regras para os segredos plantados:

1. São **falsos**, mas com formato válido (passam pelo regex do provedor).
2. Ficam num arquivo `SECRETS_UNDER_TEST.py` único, como constantes — é a lista que
   os testes usam para varrer as superfícies.
3. Nenhum é um segredo real, e o `pre-commit` do próprio RAGX tem exceção explícita
   para esse diretório — registrada e comentada.

## Os cinco testes de bloqueio

Escritos na **Fase 0** com `xfail` nas superfícies ainda inexistentes. Cada fase
posterior tem como *definition of done* virar seu `xfail` em `pass`.

```python
SURFACES = [
    ("database",   lambda db: db.execute("SELECT content FROM chunks")),
    ("embeddings", lambda db: db.execute("SELECT c.content FROM chunks c JOIN embeddings e ON e.chunk_id = c.id")),
    ("graph",      lambda db: db.execute("SELECT name, qualified_name, summary FROM entities")),
    ("mcp",        lambda db: call_every_mcp_tool_with(SECRETS)),
    ("export",     lambda db: unzip_and_grep("out.rag", SECRETS)),
    ("knowledge",  lambda db: grep_tree("knowledge/", SECRETS)),        # Fase 9
    ("federation", lambda db: grep_tree("knowledge/federation/", SECRETS)),  # Fase 11
    ("hub",        lambda db: query_hub_from_other_project(SECRETS)),   # Fase 11
]

@pytest.mark.parametrize("name,probe", SURFACES)
def test_no_secret_reaches_surface(indexed_secret_project, name, probe):
    for secret in SECRETS_UNDER_TEST:
        assert secret not in dump(probe(indexed_secret_project)), f"{secret!r} vazou em {name}"
```

Complementos obrigatórios:

- **Teste de ausência de falso negativo**: `.env.example`, `src/app.py` e
  `docs/setup.md` **precisam** estar indexados. Um gate que bloqueia tudo passa no
  teste acima e é inútil.
- **Teste do próprio relatório**: nenhum segredo aparece em `security_events`,
  em `.ragx/logs/**` nem no stdout de `ragx security scan`.
- **Teste de isolamento entre projetos** (Fase 11): dois projetos registrados no hub,
  um deles contendo a fixture de segredos. Nenhuma consulta feita a partir do outro
  projeto, em nenhum `scope`, pode retornar qualquer coisa da fixture. E projeto
  marcado `visibility = "private"` é invisível inclusive em `project:<nome>` explícito.

## Testes de orçamento de tamanho

Categoria própria, porque o teto do Git é requisito de produto
(ver [16 — Orçamento de tamanho](16-orcamento-de-tamanho.md)):

```python
def test_knowledge_cabe_no_orcamento(repo_sintetico_100k_chunks):
    assert total_bytes("knowledge/") < 50 * MB

def test_nenhum_artefato_acima_do_limite():
    assert max(f.stat().st_size for f in walk("knowledge/")) <= 20 * MB

def test_diff_minimo_por_alteracao(repo_git):
    # alterar 1 arquivo altera 1 shard de embeddings entre 16
    alterar("src/Auth/AuthService.php"); run("ragx index . && ragx sync")
    shards = [f for f in git_changed() if "embeddings/shard-" in f]
    assert len(shards) == 1

def test_reindexacao_sem_mudancas_nao_gera_diff(repo_git):
    run("ragx index ."); assert git_diff("knowledge/") == ""

def test_recusa_ao_estourar(repo_gigante):
    r = run("ragx index .")
    assert r.exit_code == 1 and "excede fail_total_bytes" in r.stdout
    assert not escreveu_nada("knowledge/")   # recusa, não trunca

def test_busca_apos_clone_sem_embedder(clone_limpo, sem_ollama):
    # só os vetores int8 versionados; sem rede
    assert run("ragx search 'autenticação'").hits > 0
```

Regressão de tamanho também é regressão: o CI publica o tamanho de `knowledge/` do
repositório de referência e falha se crescer mais de 20% sem justificativa.

## Testes arquiteturais

Verificam invariantes de design que nenhum teste funcional pega:

```python
def test_mcp_nao_acessa_filesystem():
    imports = collect_imports("src/ragx/mcp")
    assert not (imports & {"os", "subprocess", "pathlib", "requests", "httpx", "socket"})

def test_apenas_dois_modulos_leem_o_projeto():
    readers = modules_calling({"open", "Path.read_bytes", "Path.read_text"})
    assert readers <= {"ragx.indexing.walker", "ragx.sync.incremental"}

def test_domain_nao_importa_infra():
    assert not collect_imports("src/ragx/core") & infra_modules()

def test_toda_leitura_passa_pelo_gate():
    # AST: em walker.py, nenhum caminho de código entrega bytes sem chamar gate.admit()
    assert walker_calls_gate_before_yield()
```

## Determinismo

```python
def test_ids_estaveis_entre_plataformas(snapshot):
    # snapshot commitado no repo, gerado uma vez e revisado
    assert chunk_ids(fixture) == snapshot
```

CI roda em `ubuntu-latest` e `windows-latest`. Divergência de ID entre os dois é
falha de build, não curiosidade — é o que quebraria o merge no Git.

## Performance (guard rails, não benchmark)

Limites checados em CI sobre um repositório sintético de 5.000 arquivos:

```text
index (frio)                    < 180 s
index (sem mudanças)            < 5 s
search hybrid (10k chunks)      < 300 ms
build_context 3k tokens         < 1,5 s
mcp cold start                  < 1 s
sync após clone (reidratação)   < 30 s    para 10k chunks
hub sync (5 projetos)           < 10 s
search --scope all (5 projetos) < 800 ms
knowledge/ com 100k chunks      < 50 MB
```

Regressão > 30% falha o build. Valores são da máquina de referência do CI, não
absolutos.

## Robustez

Casos que precisam ter teste próprio porque são os que quebram em produção:

```text
arquivo com BOM / UTF-16 / latin-1
arquivo de 1 byte · arquivo vazio · arquivo sem newline final
CRLF misturado no mesmo arquivo
caminho com espaço, acento, emoji
caminho longo no Windows (> 260 chars)
symlink circular · symlink para fora da raiz
arquivo modificado durante a indexação
disco cheio no meio de um lote
Ctrl+C no meio da indexação → banco consistente
embedder offline → degrada para keyword com aviso, não crasha
banco corrompido → mensagem clara + sugestão de ragx reset
duas instâncias indexando o mesmo projeto → lock, não corrupção
```

## Qualidade estática

```bash
ruff check . && ruff format --check .
mypy --strict src/ragx/core src/ragx/security
mypy src/ragx                       # não-strict no resto
pip-audit                           # CVE em dependências
bandit -r src/ragx                  # padrões inseguros
```

`mypy --strict` só em `core/` e `security/` é escolha deliberada: são os módulos
onde um `None` inesperado tem consequência de segurança.

## Pipeline de CI

```text
lint  →  unit  →  security (BLOQUEANTE)  →  integration  →  e2e  →  perf  →  eval (informativo)
```

`security` roda antes de `integration` de propósito: falha rápido, e falha no lugar
certo.

## Checklist de release

```text
[ ] Todas as suítes verdes em Linux e Windows
[ ] Nenhum xfail restante nos testes de segurança
[ ] Cobertura security/ >= 90%
[ ] CHANGELOG atualizado
[ ] Versão bumpada (SemVer) em pyproject.toml e meta.ragx_version
[ ] Migrações testadas de cada versão anterior suportada
[ ] ragx doctor limpo em máquina zerada
[ ] docs/ revisados contra o comportamento real
[ ] pip-audit sem CVE de severidade alta
[ ] Pacote instalável: uv tool install ragx && ragx --version
```

## Critério de aceite da Fase 10

1. Zero `xfail` na suíte de segurança.
2. CI verde nos dois sistemas operacionais.
3. Guard rails de performance dentro do limite.
4. `ragx doctor` diagnostica ambiente incompleto com mensagem acionável.
5. Instalação limpa, em máquina sem RAGX, executa `init → index → search → mcp`
   seguindo apenas o README.
