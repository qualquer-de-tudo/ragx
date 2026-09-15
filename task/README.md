# Board de tarefas — RAGX

96 tarefas, 14 fases, ~76 dias de esforço para um desenvolvedor.
Índice completo em [BACKLOG.md](BACKLOG.md) · plano em [../docs/roadmap.md](../docs/roadmap.md).

## Estrutura

```text
task/
├── README.md                          este arquivo
├── BACKLOG.md                         índice de todas as tarefas + marcos
├── fase-00-fundacao-seguranca/        11 tarefas · RAGX-0001 .. 0011
├── fase-01-indexacao/                 14 tarefas · RAGX-0012 .. 0023, 0069, 0070
├── fase-02-busca/                      9 tarefas · RAGX-0024 .. 0031, 0071
├── fase-03-grafo/                      6 tarefas · RAGX-0032 .. 0037
├── fase-04-context-engine/             5 tarefas · RAGX-0038 .. 0042
├── fase-05-dictionary/                 3 tarefas · RAGX-0043 .. 0045
├── fase-06-mcp/                        4 tarefas · RAGX-0046 .. 0049
├── fase-07-agent-training/             5 tarefas · RAGX-0050 .. 0054
├── fase-08-export-import/              4 tarefas · RAGX-0055 .. 0058
├── fase-09-git-sync/                   4 tarefas · RAGX-0059 .. 0062
├── fase-10-hardening/                  6 tarefas · RAGX-0063 .. 0068
├── fase-11-multiprojeto-federacao/     9 tarefas · RAGX-0072 .. 0080
├── fase-12-autonomia-e-conhecimento-base/  5 tarefas · RAGX-0081 .. 0085
└── fase-13-task-analyzer-orquestracao/    11 tarefas · RAGX-0086 .. 0096
```

Um arquivo por tarefa. ID sequencial e **imutável** — os IDs não são contíguos por
fase de propósito: `RAGX-0069`, `0070` e `0071` são posteriores na numeração e
anteriores na execução, porque foram acrescentados às Fases 1 e 2 depois. Mudar o
ID quebraria as dependências que apontam para ele.

## Anatomia de uma tarefa

```text
Cabeçalho     fase, prioridade, estimativa, depende de, bloqueia, docs, status
Objetivo      por que a tarefa existe, em uma frase
Entregáveis   o que precisa existir ao final (checklist)
Fora escopo   o que NÃO é desta tarefa — evita expansão silenciosa
Aceite        como se verifica que ficou pronto (checklist)
Testes        o que precisa ter teste
Notas         contexto extra, armadilhas, decisões
DoD           checklist fixo, igual para todas
```

`Bloqueia` é calculado a partir de `Depende de` — não editar à mão. Se mudar uma
dependência, regenere o board (ver abaixo).

## Status

```text
todo        não começou
doing       em andamento (um por pessoa por vez)
review      implementado, aguardando revisão
blocked     travado — a nota precisa dizer por quê e por quem
done        DoD inteiramente marcado
```

Atualize o campo `Status` no arquivo da tarefa **e** a coluna correspondente em
`BACKLOG.md`.

## Prioridades

| Prio | Significado |
|------|-------------|
| `P0` | bloqueante — a fase não fecha sem isso |
| `P1` | alta — entra na fase, pode escorregar para a seguinte com justificativa |
| `P2` | média — pode ser adiada sem quebrar a fase |

## Definition of Done (vale para todas)

```text
[ ] Todos os critérios de aceite verificados
[ ] Testes escritos e verdes em Linux e Windows
[ ] ruff e mypy limpos
[ ] Suíte security/ continua verde
[ ] Documentação da fase confere com o comportamento implementado
```

O quarto item não é formalidade. A suíte `security/` roda em toda tarefa, de toda
fase — inclusive nas que não têm nada a ver com segurança. É assim que se garante
que nenhuma feature nova abre uma superfície nova.

## A regra dos `xfail`

`RAGX-0010` cria a suíte das superfícies de vazamento com `xfail` naquelas que ainda
não existem. Cada fase posterior tem como condição de fechamento **virar o seu
`xfail` em `pass`**:

| Superfície | Vira `pass` em | Fase |
|-----------|---------------|------|
| `database` | `RAGX-0021` | 1 |
| `embeddings` | `RAGX-0027` | 2 |
| `graph` | `RAGX-0034` | 3 |
| `mcp` | `RAGX-0049` | 6 |
| `export` | `RAGX-0056` | 8 |
| `knowledge` | `RAGX-0059` | 9 |
| `federation` | `RAGX-0073` | 11 |
| `hub` | `RAGX-0078` | 11 |

Oito superfícies ao final. Zero `xfail` restante é critério de release (`RAGX-0068`);
as duas últimas fecham na `RAGX-0078`.

## As duas restrições transversais

Além da segurança, duas restrições valem em toda fase e não têm fase própria:

**Orçamento de tamanho** ([doc 16](../docs/16-orcamento-de-tamanho.md)). Nada que
seja gravado em `knowledge/` pode estourar o teto do Git. Entra na Fase 1
(`RAGX-0070`) porque decide o que pode ser gravado, não como otimização posterior.
Toda tarefa que grave artefato versionado precisa manter `ragx size --check` verde.

**Identidade de projeto** ([doc 17](../docs/17-multiprojeto-e-federacao.md)). O
`project_id` entra na Fase 1 (`RAGX-0069`), muito antes da Fase 11 que o consome.
É uma tarefa de 2 horas que evita migrar o schema e reindexar tudo depois.

## Ordem de execução

Siga o `Depende de` de cada tarefa. O caminho crítico até o MVP vertical:

```text
0001 → 0002 → 0004 ─┐
              0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0012 → 0013 ─┐
0001 → 0003 ────────┘                                                │
                                                                     ▼
                              0014 ─┐                    0019, 0020 → 0021 → 0022 → 0023
                       0015..0018 ──┘                                          │
                                                                               ▼
                                       0024 → 0025 → 0027 ─┐
                                              0028 ────────┴─► 0029 → 0030 → 0031
                                                                              ▲
                                                                     MVP vertical
```

O que dá para paralelizar com mais de uma pessoa:

- **Fase 0:** `0003` (storage) é independente de `0004`–`0008` (segurança).
- **Fase 1:** os parsers `0015`–`0018` são quatro frentes independentes;
  `0069` e `0070` também correm em paralelo a eles.
- **Fase 2:** `0027` (semântica) e `0028` (keyword) são independentes até `0029`.
- **Fases 8 e 9** podem correr em paralelo — ambas dependem só de `0045`.
- **Fase 11:** `0072`/`0073` (fatia de federação) dependem só da Fase 3 e podem
  começar bem antes do resto da fase.

## Antecipar a Fase 11

A Fase 11 vem por último por dependência, não por importância. Em ambiente com
muitos repositórios ela pode ser puxada para logo depois da Fase 6. O que ela
exige de antes:

```text
RAGX-0069  identidade de projeto        Fase 1
RAGX-0034  extrator referencial         Fase 3   (rotas e eventos)
RAGX-0043  dictionary                   Fase 5
RAGX-0047  ferramentas MCP              Fase 6
RAGX-0061  ragx sync                     Fase 9   ← só para RAGX-0074 em diante
```

`RAGX-0072` e `RAGX-0073` (extração da superfície + fatia versionada) já entregam
valor sozinhas: o projeto passa a publicar seus contratos mesmo antes de existir hub.

## Como alterar o board

As tarefas foram geradas por script a partir de definições estruturadas. Para
mudanças pequenas (marcar um checkbox, mudar status, ajustar um critério), **edite
o arquivo Markdown diretamente** — é a fonte a partir daqui.

Para mudanças estruturais (nova tarefa, mudança de dependência), acrescente o
arquivo seguindo o mesmo template e atualize `BACKLOG.md`, incluindo a coluna
`Bloqueia` das tarefas afetadas.

## Relação com a documentação

Cada tarefa aponta para os documentos que a especificam. A documentação é a fonte
de verdade do **o quê** e do **por quê**; a tarefa é a fonte de verdade do
**quando** e do **pronto ou não**.

Divergência entre as duas é sempre bug de uma delas — e `RAGX-0068` existe
justamente para varrer o que sobrou.
