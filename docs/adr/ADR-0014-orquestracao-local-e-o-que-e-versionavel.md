# ADR-0014 — Orquestração local: segundo banco e o que é versionável

- **Status:** aceito
- **Data:** 2026-09-15
- **Contexto:** Fase 13 — Task Analyzer e Orquestração
- **Relacionado:** [ADR-0002](ADR-0002-sqlite-como-store-unico.md), [ADR-0010](ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md), [ADR-0012](ADR-0012-poder-do-agente-sobre-o-indice.md)

## Contexto

A orquestração de tarefas precisa de estado: fila, tentativas, locks, logs,
resultado. Duas perguntas aparecem imediatamente, e as duas têm resposta
contraintuitiva.

1. Esse estado vai no `knowledge.db` que já existe?
2. O que dele vai para o Git?

O [ADR-0002](ADR-0002-sqlite-como-store-unico.md) decidiu "SQLite único como
store". Este ADR abre uma exceção, e precisa justificá-la.

## Decisão 1 — dois bancos

```
.ragx/knowledge.db      conhecimento    derivado, reconstruível, leitura pesada
.ragx/ragx.sqlite       orquestração    estado vivo, escrita constante
```

O ADR-0002 valia contra fragmentar o **conhecimento**. Orquestração não é
conhecimento; é estado operacional, com padrão de acesso oposto:

| | `knowledge.db` | `ragx.sqlite` |
|---|---|---|
| Escrita | em lote, durante `index`/`sync` | contínua, a cada evento |
| Leitura | busca vetorial, varredura | consultas curtas por chave |
| Reconstrução | `ragx sync` reconstrói tudo | definição sim, execução não |
| Ciclo de vida | apagável a qualquer momento | histórico tem valor |

Misturar teria três custos concretos:

- `ragx vacuum` roda `VACUUM`, que **bloqueia o banco inteiro**. Com o worker
  ativo, ou o vacuum falha ou o dispatcher trava.
- `ragx reset` apaga `.ragx/` para reconstruir o índice. Isso é seguro
  justamente porque o índice é derivado — e apagaria junto o histórico de
  execução, que não é.
- A reindexação reescreve centenas de milhares de linhas. O worker faria
  `busy_timeout` contra ela a cada ciclo.

Cada banco mantém seu próprio `PRAGMA user_version` e sua própria sequência de
migrações.

## Decisão 2 — a definição é versionada; a execução não

Este é o ponto que decide se o sistema funciona em equipe.

```
DEFINIÇÃO (conhecimento)            EXECUÇÃO (estado local)
projects                            task_runs
tasks                               task_attempts
task_dependencies                   task_logs
acceptance_criteria                 task_events
decisions                           locks (locked_by, lease)
                                    retry_count, next_retry_at
   ↓                                   ↓
knowledge/tasks/*.json              só .ragx/ragx.sqlite
VERSIONADO no Git                   NUNCA versionado
```

**Por que a definição é versionada.** "Implementar o módulo de telemedicina em
12 tarefas, com estas dependências e estes critérios de aceite" é a decomposição
de um problema — exatamente o tipo de conhecimento que o RAGX existe para
preservar. Se vivesse só no SQLite local, sumiria no `ragx reset`, não chegaria
ao colega e não seria revisável em pull request.

**Por que a execução não é.** "A tentativa 2 da TASK-004 falhou às 14h32 na
máquina do João" não é derivável de nada, não interessa a mais ninguém, e
versionar produziria conflito de merge em todo pull request. Pior: seria um
convite a resolver conflito num arquivo de estado, que é o erro que o
[ADR-0010](ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) já
evitou para chunks.

**Como a §11 do pedido é honrada.** O pedido diz "após `git pull`, o RAGX deve
conseguir reconstruir o banco com `ragx sync`". Isso vale — e vale para o que é
reconstruível. Depois de um `ragx sync`:

- tarefas, dependências, critérios e decisões voltam idênticas, do Git
- status volta ao que o Git registrou (`pending`, `completed`…)
- histórico de execução local **não** volta, e a saída diz isso em vez de
  fingir

Um `ragx reset` seguido de `ragx sync` devolve um board íntegro e um histórico
vazio. Isso é a verdade, e é o que será impresso.

## Decisão 3 — status é versionado; lease não

Uma sutileza que decide se o merge funciona. `tasks.status` viaja no Git
(saber que a TASK-003 foi concluída é informação de time). `locked_by`,
`lock_expires_at` e `retry_count` **não** — são de uma máquina e de um instante.

Conflito em `status` entre duas branches resolve por precedência declarada, não
por escolha manual:

```
cancelled > completed > failed > blocked > running > ready > pending
```

O estado mais avançado ganha, exceto `cancelled`, que é uma decisão humana e
sobrepõe tudo. `running` que veio do Git vira `pending` na reidratação: não
existe execução rodando em outra máquina que valha para esta.

## Consequências

**Positivas**

- `ragx vacuum`, `ragx reset` e `ragx index` continuam operando sem coordenar
  com o worker.
- O board é revisável em pull request, como código.
- Perder `.ragx/` continua sendo inofensivo — agora com uma perda declarada.

**Negativas aceitas**

- Dois arquivos de banco, duas sequências de migração. O custo é real e é
  menor que o de um `VACUUM` derrubando o dispatcher.
- `knowledge/tasks/` cresce com o projeto. Mitigado: um arquivo por tarefa,
  shardado como o resto (`ADR-0010`), e tarefa concluída há mais de N dias
  pode ser arquivada com `ragx task archive`.
- Histórico de execução não sobrevive a `ragx reset`. Documentado no próprio
  comando, que passa a avisar.

## Alternativas descartadas

**Tudo no `knowledge.db`.** Simplicidade aparente, e o `VACUUM` contra o worker
é um bug que só aparece em produção, sob carga, na pior hora.

**Tudo versionado, inclusive execução.** Todo pull request traria conflito em
`task_runs`. Resolver conflito de log é trabalho sem valor.

**Nada versionado.** É o que a §11 do pedido sugere ao pé da letra, e quebra a
promessa central do RAGX: o conhecimento sobrevive à máquina. Uma decomposição
de projeto que existe só em `.ragx/` é conhecimento perdido no primeiro reset.
