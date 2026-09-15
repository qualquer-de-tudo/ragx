# RAGX-0084 — Base de conhecimento `agents`, otimizada

| | |
|---|---|
| **Fase** | 12 — Autonomia + Conhecimento base |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0081` |
| **Bloqueia** | — |
| **Documentação** | [18-conhecimento-base.md](../../docs/18-conhecimento-base.md) |
| **Status** | `done` (com pendência de publicação) |

## Objetivo

Transformar `github.com/renan-s-oliveira/agents` — a "constituição" do agente —
em conhecimento base efetivamente utilizável e indexado pelo RAGX.

## Diagnóstico do estado recebido

34 arquivos, 2.699 linhas. **14 deles eram apenas um título e um parêntese de
intenção:**

```
core/standards.md, core/architecture.md, core/patterns.md,
ai/approval-flow.md, ai/security-red-team.md, ai/security-blue-team.md,
ai/module-doc-generator.md, engineering/testing.md, engineering/validations.md,
engineering/performance.md, engineering/refactoring.md,
quality/observability.md, quality/risk-analysis.md, quality/auto-improvements.md
```

Um agente que carregasse `core/patterns.md` recebia literalmente
`(Padrões obrigatórios e anti-patterns)`. O README descrevia um sistema que o
conteúdo não sustentava.

## Entregáveis

- [x] Os 14 arquivos escritos — regra por regra, com exemplo concreto
- [x] **IDs estáveis** em toda regra (`R-ARC-01`, `A-PAT-05`, `R-VAL-09`…), citáveis em plano, revisão e débito — e encontráveis por busca literal **e** semântica
- [x] `ai/ragx-integration.md` — como o agente usa o índice; era a peça que faltava
- [x] `MANIFEST.yaml` — roteamento: 4 arquivos sempre em contexto, o resto por gatilho
- [x] README: tabela de prefixos, novos arquivos, referência ao manifesto
- [x] Instalado como fonte base `agents`, indexado sob `@base/agents/`
- [x] `base-knowledge/` excluído do índice do projeto (senão cada documento apareceria duas vezes)

## Decisões de formato

**IDs estáveis.** `R-VAL-09` é citável e verificável. "boa prática de
segurança" não é. Também melhora a recuperação: o ID é um token literal que a
busca por palavra-chave acha com precisão, e o texto ao redor dá o sinal
semântico.

**Manifesto de roteamento.** Carregar os 35 arquivos em toda tarefa gasta o
contexto antes de começar. `always` tem 4 arquivos; o resto é por gatilho.

**Precedência explícita.** Instrução do humano > código do projeto > esta base >
conhecimento geral. Está no manifesto e em `R-RGX-07`: quando a base e o
projeto divergem, **o projeto ganha**.

## Critérios de aceite

- [x] Nenhum arquivo é stub
- [x] Busca por `"regra de validação de identificador de outra entidade IDOR"` devolve `@base/agents/engineering/validations.md`
- [x] 36 documentos sob `@base/agents/`, zero sob `base-knowledge/`
- [x] `knowledge/base.json` carrega a URL do repositório
- [x] Toda referência cruzada entre arquivos aponta para arquivo existente

## Pendência (fora do alcance desta tarefa)

O conteúdo otimizado está em `base-knowledge/agents/` **deste** repositório. A
fonte instalada aponta para esse caminho local. Para que outras máquinas
recebam a versão otimizada, o conteúdo precisa ser publicado em
`github.com/renan-s-oliveira/agents` — o que exige credencial que o agente não
tem e não deve ter.

Até lá, `ragx base sync` em outra máquina traz a versão **antiga** do GitHub.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [x] Indexação verificada com busca real
- [x] Documentação confere com o comportamento
- [ ] Conteúdo publicado no repositório de origem — **ação do humano**
