# 20 — Task Analyzer

> A porta de entrada de toda solicitação. Decide **executar agora** ou
> **documentar e decompor antes**.
> Ver [21 — Orquestração](21-orquestracao-de-tarefas.md) e
> [ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md).

## A pergunta

Antes de qualquer coisa, uma só:

> É melhor executar isto agora, ou primeiro transformar em conhecimento
> estruturado e tarefas executáveis?

A pergunta é interna. O agente decide por critério objetivo, não perguntando ao
humano a cada pedido — mas registra **quais fatores** levaram à decisão, para
que ela possa ser contestada.

## O que ele não é

Não é um LLM. O RAGX não tem um e não vai ter
([ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)). O classificador é
**determinístico**: sinais léxicos declarados em YAML, somados a evidência
extraída do próprio índice.

Isso tem uma consequência boa e uma limitação honesta:

- **Boa:** a mesma solicitação sempre recebe a mesma classificação, offline, em
  milissegundos, e o motivo é auditável linha a linha.
- **Limitação:** ele lê palavras e mede o impacto no repositório. Não entende o
  pedido. Uma solicitação escrita de forma incomum pode ser subestimada.

Por isso o agente pode sobrepor a classificação (`ragx task analyze --as`, ou
`analyze_request` via MCP com `override`), e a sobreposição fica registrada com
justificativa.

## Classificação

```text
DIRECT_EXECUTION            faz agora
ANALYSIS_REQUIRED           entende antes de escrever
DOCUMENTATION_REQUIRED      documenta antes de implementar
TASK_DECOMPOSITION_REQUIRED quebra em tarefas
ARCHITECTURAL_CHANGE        toca a estrutura
PRODUCT_CHANGE              toca regra de negócio ou jornada
SECURITY_CHANGE             toca autenticação, autorização, dado pessoal
PERFORMANCE_CHANGE          toca o que roda por item
UNKNOWN                     sinal insuficiente
```

Saída:

```json
{
  "classification": "DOCUMENTATION_REQUIRED",
  "complexity": "high",
  "requires_documentation": true,
  "requires_decomposition": true,
  "requires_approval": true,
  "confidence": 0.81,
  "reasoning_summary": "Toca autenticação e cria módulo novo; 3 módulos existentes referenciam o assunto.",
  "risks": ["altera autenticação", "cria módulo novo"],
  "dependencies": ["src/auth/session.py", "docs/02-seguranca.md"],
  "scores": { "architecture": 30, "security": 25, "dependency": 12, "...": 0 },
  "strategy": "DOCUMENT -> DECOMPOSE -> EXECUTE"
}
```

`reasoning_summary` é uma frase operacional montada a partir dos sinais que
dispararam. Não é raciocínio de modelo, e não pretende ser.

## Os sete scores

Cada um de 0 a 100, declarados em
[`src/ragx/tasks/signals.yaml`](../src/ragx/tasks/signals.yaml) — mesmo idioma
de `intents.yaml` do Context Engine.

| Score | Do que vem |
|---|---|
| `complexity` | verbos de criação, quantidade de entregáveis distintos, tamanho do pedido |
| `architecture` | "novo módulo", "migrar", "integrar", "refatorar", "mudar banco" |
| `business_rule` | "regra de negócio", "fluxo", "jornada", "cobrança", "imposto" |
| `dependency` | **medido no índice**: quantos módulos referenciam o assunto |
| `risk` | irreversibilidade — migration, deleção, mudança de contrato |
| `security` | autenticação, autorização, LGPD, segredo, permissão, criptografia |
| `documentation` | ausência de documento no índice cobrindo o assunto |

`dependency` e `documentation` são os dois que **usam o RAG**, e são os que
tornam o analisador mais que um casador de palavras: a mesma frase pontua
diferente em um repositório onde o assunto já aparece em cinco módulos e em um
onde não aparece em lugar nenhum.

### Do score à estratégia

```text
 0 – 25    DIRECT_EXECUTION
26 – 50    ANALYSIS_REQUIRED
51 – 75    DOCUMENTATION_REQUIRED
76 – 100   DOCUMENTATION_REQUIRED + TASK_DECOMPOSITION_REQUIRED
```

Com duas exceções que **ignoram a faixa**, porque errar nelas é caro demais:

- `security >= 40` → nunca `DIRECT_EXECUTION`, e `requires_approval = true`
- `risk >= 60` (migration, deleção, contrato) → `requires_approval = true`

O total é a média ponderada, não a soma: um pedido que dispara só um sinal forte
não vira projeto por causa disso.

## Não transformar tudo em projeto

Metade do valor está aqui. Um typo tem que continuar sendo um typo.

```text
Corrigir um erro de digitação            →  DIRECT_EXECUTION
Mudar o texto de uma mensagem            →  DIRECT_EXECUTION
Adicionar um campo opcional              →  DIRECT_EXECUTION
Criar um teste para função existente     →  DIRECT_EXECUTION
Entender como funciona o pagamento       →  ANALYSIS_REQUIRED
Otimizar a listagem de faturas           →  DOCUMENTATION_REQUIRED
Implementar módulo de telemedicina       →  DOCUMENT → DECOMPOSE → EXECUTE
```

Sinais de **redução** existem e são explícitos em `signals.yaml`: "typo",
"renomear variável", "ajustar mensagem", "corrigir comentário" derrubam o score
mesmo que outra palavra do pedido tenha subido.

## Fluxo

```text
Solicitação
     ↓
detect signals ──────────► signals.yaml (léxico)
     ↓
measure impact ──────────► search + graph (índice real)
     ↓
score 7 dimensões
     ↓
┌──────────────┬────────────────────────────────┐
│ ≤ 25         │ > 25                           │
▼              ▼                                │
DIRECT      buscar conhecimento existente       │
executa     (RAG: docs, ADRs, entidades)        │
            ↓                                   │
            gerar documentação                  │
            ↓                                   │
            indexar (Security Gate → grafo)     │
            ↓                                   │
            decompor em tarefas                 │
            ↓                                   │
            dependências, prioridade, aceite    │
            ↓                                   │
            board pronto ──────────────────────►│
```

## Documentação nunca nasce isolada

Quando o analisador decide documentar, o plano **parte do que já existe**:

```text
solicitação
   ↓ search_hybrid          documentos e código relacionados
   ↓ get_entity             entidades tocadas e suas relações
   ↓ dictionary             tecnologias, serviços, convenções
   ↓ decisions              ADRs que já decidiram parte do assunto
   ↓ tasks                  tarefas anteriores no mesmo território
   ↓
plano de documentação
```

O `DocumentationPlanner` produz **esqueletos com o contexto já dentro** — cada
documento nasce com as seções obrigatórias do seu tipo, as referências
encontradas e as lacunas marcadas como pendência explícita. O conteúdo é
escrito pelo agente, na tarefa correspondente; o RAGX não inventa texto.

Um documento que o planner não conseguiu fundamentar sai marcado:

```markdown
> **Pendente:** nenhum documento existente cobre o fluxo de agendamento.
> Esta seção precisa de entrevista com o time antes de ser escrita.
```

## Tipos de documento

```text
product      business     requirements   architecture   technical
database     api          security       performance    testing
deployment   operations   decision       migration      integration
```

Cada tipo tem seções obrigatórias declaradas em `doctypes.yaml`, e cada um
sabe de que outro tipo costuma depender — é o que permite ao planner produzir
`architecture` antes de `technical`, e `technical` antes de `database`.

Vão para `knowledge/<tipo>/`, versionados, e passam pelo pipeline normal:

```text
documento → Security Gate → parser → chunker → embedding → grafo → índice
```

Sem atalho. Documento gerado pelo RAGX é entrada como qualquer outra.

## CLI

```bash
ragx task analyze "Implementar novo módulo de telemedicina"
```

```text
Análise — "Implementar novo módulo de telemedicina"

  Classificação   DOCUMENTATION_REQUIRED + TASK_DECOMPOSITION_REQUIRED
  Complexidade    high          Confiança  0.81
  Estratégia      DOCUMENT → DECOMPOSE → EXECUTE

  Scores          arquitetura  72   ███████▏
                  complexidade 68   ██████▊
                  dependência  34   ███▍
                  segurança    25   ██▌
                  risco        20   ██
                  regra        45   ████▌
                  documentação 80   ████████

  Por quê         cria módulo novo · toca dado pessoal (LGPD) ·
                  4 módulos existentes referenciam "agendamento" ·
                  nenhum documento cobre o assunto

  Sugerido        4 documentos · 12 tarefas · 18 dependências

  Nada foi criado. Para aplicar:
    ragx task plan "Implementar novo módulo de telemedicina" --apply
```

`analyze` **não escreve nada**. Quem escreve é `ragx task plan --apply`.

## Ver também

- [21 — Orquestração de tarefas](21-orquestracao-de-tarefas.md)
- [ADR-0014](adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md)
- [ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)
- [07 — Context Engine](07-context-engine.md) — de onde vem `intents.yaml`
