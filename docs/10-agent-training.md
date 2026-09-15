# 10 — Agent Knowledge Training (Fase 7)

## Nomenclatura, primeiro

Isto **não é treinamento de modelo**. Não há gradiente, não há peso ajustado, não há
fine-tuning. O nome correto é:

> **Agent Knowledge Training** — curadoria e empacotamento de conhecimento,
> regras e exemplos que condicionam o comportamento de um agente em um projeto.

Chamar de "treinamento de modelo" criaria expectativa errada sobre custo,
tempo e resultado. O que se produz aqui é um **perfil de agente** versionável.

## O que compõe um perfil

```text
Project Knowledge      o que existe no repositório (índice + grafo)
Product Knowledge      o que o produto faz e para quem
Business Rules         regras de negócio que o código precisa respeitar
Architecture           camadas, fronteiras, decisões (ADRs)
Security Rules         o que nunca pode ser feito
Coding Standards       convenções detectadas + declaradas
Examples               pares tarefa → solução aceita
Skills                 procedimentos passo a passo para tarefas recorrentes
```

## Estrutura

```text
agents/
└── backend-architect/
    ├── manifest.json          # identidade, versão, escopo, fontes
    ├── instructions.md        # prompt de sistema do agente
    ├── dictionary.json        # recorte do dicionário do projeto
    ├── rules/
    │   ├── security.md
    │   ├── architecture.md
    │   └── coding-standards.md
    ├── skills/
    │   ├── criar-endpoint.md
    │   └── adicionar-migration.md
    ├── examples/
    │   ├── 001-novo-service.md
    │   └── 002-refatorar-controller.md
    └── evaluation/
        ├── cases.yaml
        └── results/
```

Tudo em Markdown e JSON, tudo versionado no Git. Um perfil é revisável em pull request.

### `manifest.json`

```json
{
  "schema_version": 1,
  "name": "backend-architect",
  "version": "3",
  "description": "Agente para desenho e implementação de serviços backend neste projeto.",
  "scope": {
    "include_paths": ["src/**", "docs/architecture/**", "database/**"],
    "exclude_paths": ["src/Legacy/**"],
    "languages": ["php", "sql"]
  },
  "knowledge": {
    "index_run": 42,
    "dictionary_hash": "9c1f...",
    "chunks": 612,
    "entities": 180
  },
  "context_policy": {
    "default_tokens": 6000,
    "graph_depth": 2,
    "prefer": ["docs/architecture", "src/Auth"]
  },
  "generated_at": "2026-09-15T12:40:00Z",
  "generated_by": "ragx 0.7.0"
}
```

## Comandos

```bash
ragx agent create backend-architect            # esqueleto interativo
ragx agent train backend-architect             # compila conhecimento no perfil
ragx agent show backend-architect
ragx agent list
ragx agent eval backend-architect              # roda a suíte de avaliação
ragx agent export backend-architect            # perfil portátil
```

## O que `ragx agent train` faz

```text
Documentação do projeto
      ↓  filtra por manifest.scope
Knowledge (chunks + grafo)
      ↓
Dictionary recortado          só o que é relevante ao escopo do agente
      ↓
Rules                         security.md sempre incluído, sem opção de remover
      ↓
Skills                        procedimentos inferidos de padrões repetidos + escritos à mão
      ↓
Examples                      extraídos do histórico Git (commits que seguem o padrão)
      ↓
instructions.md               montado a partir de template + tudo acima
      ↓
Agent Profile                 gravado em agents/<nome>/, com manifest versionado
```

Detalhes importantes:

- **Regras escritas à mão nunca são sobrescritas.** `train` gera para
  `rules/*.generated.md` e faz merge explícito; o arquivo curado manualmente vence.
- `rules/security.md` é **obrigatório** e derivado do ruleset do RAGX. Um perfil sem
  ele não compila.
- `examples/` extraídos do Git são propostas: entram como `examples/_proposed/` e
  precisam de promoção manual. Exemplo ruim ensina padrão ruim.
- `instructions.md` referencia o MCP em vez de embutir conhecimento:
  *"use `get_dictionary` antes de perguntar sobre estrutura"*. O perfil é um mapa,
  não um despejo.

## Skills

Uma skill é um procedimento repetível, escrito para ser seguido:

```markdown
---
name: criar-endpoint
triggers: ["criar endpoint", "novo endpoint", "nova rota"]
---

# Criar um endpoint

## Pré-requisitos
- [ ] Rota ainda não existe (`ragx search "<caminho>" --mode keyword`)

## Passos
1. Criar o Request de validação em `src/Http/Requests/`
2. Criar o Controller em `src/Http/Controllers/` — apenas orquestração
3. A regra de negócio vai no Service correspondente, nunca no Controller
4. Registrar a rota em `routes/api.php`
5. Escrever teste de feature em `tests/Feature/`

## Padrões a seguir
- Ver `examples/001-novo-service.md`
- Nomes: `<Recurso>Controller`, método `store`/`index`/`show`/`update`/`destroy`

## Armadilhas
- Não injetar o repositório direto no Controller (ver `rules/architecture.md`)
```

## Avaliação

Sem avaliação, um perfil é opinião. `evaluation/cases.yaml`:

```yaml
- id: eval-001
  task: "Onde fica a validação de token de autenticação?"
  expect_sources: ["src/Auth/TokenPolicy.php"]
  must_mention: ["TokenPolicy"]
  must_not_mention: ["senha", "secret"]

- id: eval-002
  task: "Como adiciono um novo endpoint de listagem?"
  expect_skill: "criar-endpoint"
  expect_sources: ["docs/architecture/api.md"]
```

`ragx agent eval` mede o que o RAGX controla — **recuperação**, não geração:

```text
eval-001  ✓  fontes esperadas recuperadas em top-3
eval-002  ✓  skill correta ativada
eval-003  ✗  fonte esperada em posição 7 (esperado <= 3)

3 casos · 2 aprovados · Recall@3 = 0.67
```

Isso é honesto: o RAGX não avalia a qualidade da resposta do modelo, avalia se
entregou o contexto certo. Avaliar geração exigiria um LLM-as-judge, e isso fica
registrado como evolução pós-MVP.

## Segurança

- Perfil é artefato compartilhado → mesmo re-scan do Dictionary antes de gravar.
- `examples/` extraídos do Git passam pelo gate: commit antigo com segredo no diff
  **não** vira exemplo.
- `manifest.scope` nunca pode incluir caminho fora da raiz do projeto.

## Critério de aceite da Fase 7

1. `ragx agent create` + `ragx agent train` produz perfil completo e válido contra o
   JSON Schema do manifest.
2. Retreinar com índice inalterado não altera arquivos curados manualmente.
3. `ragx agent eval` roda os casos e reporta Recall@3 por caso.
4. Nenhum arquivo em `agents/**` contém segredo (teste de segurança).
5. Perfil é legível e revisável por humano em PR — sem blob, sem binário.
