# 08 — Knowledge Dictionary (Fase 5)

## O problema que resolve

Um agente que chega no projeto não sabe o que perguntar. Sem orientação, ele faz a
pergunta mais cara possível:

> "Me explique todo o projeto."

O Dictionary é um **mapa barato**: uma visão estruturada e pequena (alguns KB) que
o agente lê *antes* de gastar contexto, para descobrir o que existe e então fazer
perguntas específicas.

```text
sem dictionary:   agente → "explique o projeto" → 50k tokens → ainda perdido
com dictionary:   agente → get_dictionary (2k tokens) → "onde fica AuthService?" → 3k tokens
```

## Geração

```bash
ragx dictionary generate
ragx dictionary generate --semantic     # enriquece com LLM (opt-in)
ragx dictionary show
ragx dictionary show --section services
```

Saída em `knowledge/` (versionável no Git, ver [12 — Git Sync](12-git-sync.md)):

```text
knowledge/
├── dictionary.json      # visão consolidada — ponto de entrada
├── entities.json        # export do grafo: nós
├── relations.json       # export do grafo: arestas
├── glossary.json        # termos do domínio e siglas
└── summaries.json       # resumo por documento/módulo
```

## `dictionary.json`

```json
{
  "schema_version": 1,
  "project": {
    "name": "Meu Projeto",
    "root_hint": "monorepo PHP + TS",
    "generated_at": "2026-09-15T12:29:04Z",
    "index_run": 42
  },
  "technologies": [
    { "name": "Laravel", "version": "11.x", "evidence": ["composer.json"], "confidence": 1.0 },
    { "name": "PostgreSQL", "evidence": ["docker-compose.yml", "config/database.php"] },
    { "name": "Redis", "evidence": ["composer.json", "src/Auth/AuthService.php"] }
  ],
  "services": [
    {
      "name": "AuthService",
      "path": "src/Auth/AuthService.php",
      "summary": "Autenticação via SSO corporativo, sessão em Redis.",
      "depends_on": ["SsoProvider", "Redis"],
      "documented_by": ["docs/auth.md"]
    },
    { "name": "PaymentService", "path": "src/Payment/PaymentService.php" }
  ],
  "modules": [
    { "name": "Auth", "path": "src/Auth", "files": 12, "chunks": 84 }
  ],
  "concepts": {
    "authentication": ["SSO", "OAuth", "AuthService", "TokenPolicy"],
    "billing": ["PaymentService", "Invoice", "Stripe"]
  },
  "entrypoints": [
    { "kind": "http", "value": "POST /api/login", "handler": "LoginController.store" },
    { "kind": "cli", "value": "php artisan queue:work" }
  ],
  "data_stores": [
    { "name": "users", "kind": "table", "defined_in": "database/migrations/..." }
  ],
  "conventions": [
    { "rule": "Services em src/<Dominio>/<Nome>Service.php", "confidence": 0.9, "evidence": ["src/Auth", "src/Payment"] }
  ],
  "docs": [
    { "path": "docs/auth.md", "title": "Autenticação", "topics": ["SSO", "sessão"] }
  ],
  "stats": { "documents": 120, "chunks": 1832, "entities": 340, "relations": 890 }
}
```

## Como cada seção é derivada

| Seção | Fonte primária | Determinístico? |
|-------|----------------|-----------------|
| `technologies` | manifests de dependência (`composer.json`, `package.json`, `pyproject.toml`, `go.mod`) + catálogo do grafo | sim |
| `services` | classe com convenção de nome ou referenciada de fora, **sem** exceção, enum, DTO (`@dataclass`, classe só de campos) nem símbolo privado; ordenada pelo grau no grafo; `summary` extrativo | sim |
| `modules` | estrutura de diretórios + contagem de chunks; a pasta que concentra mais de 25% do código é aberta em mais um nível (`src/ragx` vira `src/ragx/indexing`); `summary` do README, do `__init__.py` ou do README de uma pasta-mãe (nunca o da raiz) | sim |
| `entrypoints` | rotas, `main`, scripts de `package.json`, `Dockerfile CMD` | sim |
| `data_stores` | `CREATE TABLE`, migrations, modelos ORM (sem tabelas de `tests/` e `fixtures/`) | sim |
| `concepts` | o que cada documento de `docs/` descreve: o título dele e as classes que ele documenta (relação `documented_by` do grafo), sem símbolo genérico (citado por mais de 4 documentos) | sim |
| `conventions` | detecção de padrão repetido (>= 3 ocorrências) | sim |
| `glossary` | siglas e termos de domínio extraídos de headings e docstrings | parcial |
| `summaries` | primeira seção do doc / docstring de módulo; LLM no modo `--semantic` | parcial |

**Resumos extrativos (RAGX-0109).** O `summary` de um serviço é a primeira linha do docstring da classe; sem ele, a do
docstring do módulo onde ela mora; em TS/JS/PHP, o bloco `/** ... */` que a precede. O de um módulo vem do primeiro parágrafo
do README da pasta ou do docstring do `__init__.py`. **Sem docstring, `summary` fica `null`: nada é inventado.** O `--semantic` só
melhora o que o extrativo produziu.

**Densidade (RAGX-0110).** O dicionário tem um teto de ~4.000 tokens (`_TOKEN_TARGET`): neste repositório caiu de 10.935 (auditoria)
PARA 3.701, com mais informação por item (resumo em vez de lista de símbolos). Nenhum símbolo `_privado` entra.

Regra dura: **tudo que é determinístico é gerado sem LLM**. O modo `--semantic` só
preenche `concepts`, `glossary` e `summaries`, e marca cada item com
`"source": "llm"` + `confidence`, para que o consumidor saiba o que é inferência.

## Confiança e evidência

Todo item do dicionário carrega `evidence` — a lista de caminhos que sustentam a
afirmação. Um dicionário sem evidência é um dicionário que ninguém pode auditar,
e alucinação de LLM entra exatamente por aí.

```json
{ "name": "Redis", "evidence": ["composer.json", "docker-compose.yml"], "confidence": 1.0 }
```

## Segurança

O dicionário é um artefato **compartilhado** (vai para o Git e para o `.rag`), então
é superfície de vazamento de primeira classe:

- Só consome dados já no store (que já passaram pelo gate).
- Passa por um re-scan antes de ser gravado: se um nome de entidade ou um resumo
  casar com regra de segredo, o item é descartado e um `security_event` é gravado.
- `evidence` lista caminhos, **nunca** conteúdo.
- Variáveis de ambiente são listadas por **nome**, nunca por valor
  (`DATABASE_URL` sim; o valor, nunca).

## Consumo

Por CLI:

```bash
ragx dictionary show --section services
ragx dictionary show --level 0          # o mapa em ~400 tokens
```

Por MCP (Fase 6), é a ferramenta que todo agente deve chamar primeiro:

```json
{ "tool": "get_dictionary", "arguments": { "level": 0 } }
{ "tool": "get_dictionary", "arguments": { "section": "services", "level": 1 } }
```

**Níveis (RAGX-0111).** O agente começa barato e aprofunda. Os níveis são recortes de leitura do mesmo `dictionary.json` (o
formato em disco não muda) e cada um é superconjunto do anterior:

| `level` | O que traz | Tokens (neste repositório) |
|---|---|---:|
| `0` | projeto, estatísticas, tecnologias, 8 serviços (só nomes), 6 módulos com resumo, pontos de entrada | ~400 |
| `1` | tudo do `0` + 12 serviços com caminho e resumo, todos os módulos, convenções, 10 documentos | ~1.700 |
| `2` (padrão) | o dicionário completo, como sempre foi | ~3.700 |

`section` e `level` se combinam: `section="services", level=1` devolve só os serviços no recorte do nível 1. O playbook e as
`instructions` do servidor mandam começar por `level=0`.

## Critério de aceite da Fase 5

1. `ragx dictionary generate` roda **sem nenhum LLM configurado** e produz
   `technologies`, `services`, `modules`, `entrypoints`, `data_stores` corretos
   no repositório de referência.
2. Todo item tem `evidence` não vazio.
3. `dictionary.json` completo <= 8.000 tokens em repositório de ~5k arquivos
   (se exceder, o builder agrega em vez de listar tudo).
4. Regeneração sobre índice inalterado produz arquivo **byte-idêntico**
   (chaves ordenadas, sem timestamp volátil fora de `generated_at`; o
   `generated_at` fica fora do hash de comparação e, desde a RAGX-0148, o
   arquivo nem é regravado: o mtime também não muda).
5. Nenhum valor de segredo ou de variável de ambiente aparece em qualquer arquivo
   de `knowledge/`.
