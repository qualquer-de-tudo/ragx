# agents/ — Estrutura de Contexto para Agente de IA

Esta pasta define as **regras, comportamentos, padrões e guardrails** que governam o agente de IA do projeto. Ela funciona como a "constituição" do agente: tudo que ele deve saber, respeitar e aplicar ao gerar código, revisar, planejar ou tomar decisões técnicas.

---

## Estado desta base

Todos os arquivos estão escritos. As regras carregam **ID estável**
(`R-ARC-01`, `R-VAL-09`, `A-PAT-05`…) para que possam ser citadas em plano,
revisão e débito — e encontradas por busca, literal ou semântica.

`MANIFEST.yaml` diz o que carregar sempre e o que carregar por gatilho.
Carregar os 35 arquivos em toda tarefa gasta o contexto antes de começar.

Prefixos em uso:

| Prefixo | Assunto | Arquivo |
|---|---|---|
| `R-ARC` | arquitetura e camadas | `core/architecture.md` |
| `R-PAT` / `A-PAT` | padrões / anti-patterns | `core/patterns.md` |
| `R-STD` | convenções de código | `core/standards.md` |
| `R-APR` | fluxo de aprovação | `ai/approval-flow.md` |
| `R-RGX` | uso do índice de conhecimento | `ai/ragx-integration.md` |
| `R-VAL` | validação de entrada | `engineering/validations.md` |
| `R-TST` | testes | `engineering/testing.md` |
| `R-PER` | performance | `engineering/performance.md` |
| `R-REF` | refatoração | `engineering/refactoring.md` |
| `R-RED` / `R-BLU` | red team / blue team | `ai/security-*.md` |
| `R-RSK` | análise de risco | `quality/risk-analysis.md` |
| `R-OBS` | observabilidade | `quality/observability.md` |
| `R-AIM` | sugestões proativas | `quality/auto-improvements.md` |
| `R-DOC` | documentação de módulo | `ai/module-doc-generator.md` |

---

## Por que essa estrutura existe?

Agentes de IA sem contexto estruturado tendem a tomar decisões inconsistentes, ignorar padrões do projeto e introduzir riscos. Esta estrutura resolve isso ao fornecer ao agente:

- **Regras de arquitetura e padrões** de código do projeto
- **Fluxos de aprovação** para que nenhuma ação destrutiva ocorra sem revisão humana
- **Guardrails** que bloqueiam comportamentos proibidos
- **Contexto de qualidade** para revisão, débito técnico e risco
- **Agentes especializados** para segurança, documentação e melhorias

---

## Estrutura de pastas

```
agents/
├── MANIFEST.yaml  → Roteamento: o que carregar sempre, o que carregar por gatilho
├── core/          → Fundação: arquitetura, padrões, planos e standards
├── ai/            → Comportamento do agente, fluxos, guardrails e agentes especializados
├── engineering/   → Regras técnicas: testes, segurança, performance, validações, refatoração
└── quality/       → Qualidade contínua: revisão, débito, risco, observabilidade, melhorias
```

---

## `core/` — Fundação do projeto

Contém as regras que definem como o projeto é construído. O agente deve carregar estes arquivos antes de qualquer tarefa de código.

| Arquivo | Propósito |
|---|---|
| `architecture.md` | Regras de arquitetura modular: como organizar actions, services e DTOs |
| `patterns.md` | Padrões obrigatórios e anti-patterns que devem ser evitados |
| `plans.md` | **Como conduzir o planejamento** — perguntas obrigatórias, estrutura do plano e onde salvar os arquivos gerados |
| `standards.md` | Convenções de código: PSR-12, tipagem estrita, PHPDoc e nomenclatura |

**Como usar:** ao iniciar uma nova feature ou refatoração, o agente consulta `architecture.md` e `patterns.md` para garantir consistência. O agente usa `plans.md` para conduzir o planejamento e gera um arquivo `.plan.md` separado no projeto (ex: `src/app/modules/{modulo}/plans/`). O caminho de destino é definido pelo Tech Lead ou perguntado ao programador se ainda não definido.

---

## `ai/` — Comportamento e inteligência do agente

Define como o agente deve se comportar, quais são seus limites e como agentes especializados operam.

| Arquivo | Propósito |
|---|---|
| `agent-behavior.md` | Fluxo geral do agente — 6 passos obrigatórios de qualquer tarefa, com decisão de entrada para projeto novo vs. existente |
| `new-project.md` | **Wizard de setup** — entrevista estruturada para configurar todos os arquivos de contexto de um projeto novo do zero |
| `import-project.md` | **Wizard de importação** — entrevista estruturada para mapear projeto já em andamento e atualizar todo o contexto |
| `triggers.md` | **Gatilhos por contexto** — interpreta a mensagem do programador para acionar novo projeto, importacao ou agente especifico |
| `library-references.md` | **Referencias de bibliotecas** — catalogo de links oficiais para docs de pacotes/libs/dependencias por stack |
| `module-context-reader.md` | **Leitor de contexto de módulo** — análise obrigatória do código existente antes de qualquer ação em módulo já implementado |
| `approval-flow.md` | Estados do ciclo de vida de uma ação: `DRAFT → APPROVED → EXECUTION` |
| `guardrails.md` | Bloqueios obrigatórios — o que o agente nunca pode fazer sem aprovação humana |
| `prompts.md` | Prompt base usado para inicializar o agente com todo o contexto necessário |
| `skills.md` | Habilidades do agente, incluindo a capacidade de questionar antes de agir |
| `ragx-integration.md` | **Uso do índice de conhecimento** — como consultar o RAG antes de agir, o que ele responde e o que ele deliberadamente não responde |
| `security-blue-team.md` | Agente de defesa: analisa vulnerabilidades e sugere correções com aprovação |
| `security-red-team.md` | Agente de ataque: simula ameaças, identifica falhas e registra débito se não corrigidas |
| `module-doc-generator.md` | Agente de documentação: gera docs automáticos por módulo ou feature |
| `dba.md` | **DBA Agent** — especialista em todos os paradigmas de banco de dados (SQL, NoSQL, memória, Elasticsearch, Meilisearch); pilares inegociáveis: performance, integridade e segurança |
| `dpo.md` | **DPO Agent** — especialista em proteção de dados e privacidade; suporta múltiplas legislações (LGPD, GDPR e outras); registra aceites e rejeições do programador em log por módulo |

**Como usar:**
- Projeto novo do zero: usar `new-project.md`
- Projeto existente sem contexto consolidado: usar `import-project.md`
- Projeto existente com contexto consolidado: iniciar por `module-context-reader.md`
- Qualquer contexto de banco de dados (schema, query, cache, busca): acionar `dba.md`
- Qualquer contexto de dado pessoal, privacidade ou compliance: acionar `dpo.md`

Segurança e performance são inegociáveis em ambos os fluxos de onboarding.

---

## `engineering/` — Regras técnicas de implementação

Contém as regras que o agente aplica ao escrever, revisar ou modificar código.

| Arquivo | Propósito |
|---|---|
| `performance.md` | Otimizações obrigatórias: queries N+1, cache, índices, lazy loading |
| `refactoring.md` | Regras de refatoração automática com limites claros de escopo |
| `security.md` | Regras de segurança integrando Blue Team e Red Team, com registro de débito |
| `testing.md` | Padrões de testes automatizados: cobertura mínima, tipos de testes, nomenclatura |
| `validations.md` | Validação obrigatória de inputs em todas as entradas do sistema |

**Como usar:** ao gerar ou revisar código, o agente deve verificar cada um destes arquivos para garantir que o código produzido passa nos critérios de engineering. Não deve gerar código que viole `security.md` ou `validations.md`.

---

## `quality/` — Qualidade e evolução contínua

Define como o agente monitora, registra e melhora a qualidade do projeto ao longo do tempo. Os arquivos desta pasta orientam o **comportamento do agente** — os artefatos gerados (revisões, decisões, débitos) são salvos como arquivos separados no projeto para evitar conflito entre programadores.

| Arquivo | Propósito |
|---|---|
| `auto-improvements.md` | Sugestões automáticas de melhoria que o agente pode propor proativamente |
| `code-review.md` | **Como conduzir revisões** — checklist obrigatório e onde salvar os arquivos `.review.md` gerados por programador |
| `decision-log.md` | **Como registrar decisões** — estrutura e onde salvar os arquivos `.decision.md` gerados |
| `observability.md` | Padrões de logs, métricas e rastreabilidade que o código deve implementar |
| `risk-analysis.md` | Análise de risco aplicada a mudanças e novas features |
| `tech-debt.md` | **Como registrar débitos** — classificação, prioridade e onde salvar os arquivos `.techdebt.md` gerados |

**Como usar:** cada programador gera seus próprios arquivos de revisão, decisão e débito — nunca compartilhados. Os caminhos de destino são definidos pelo Tech Lead e registrados nos respectivos arquivos de orientação. Se não houver definição prévia, o agente pergunta ao programador e sugere que o Tech Lead formalize o padrão.

### Convenção de nomes dos artefatos gerados

| Tipo | Padrão de nome |
|---|---|
| Plano | `{YYYY-MM-DD}_{slug-da-tarefa}.plan.md` |
| Revisão | `{YYYY-MM-DD}_{slug-da-tarefa}_{@programador}.review.md` |
| Decisão | `{YYYY-MM-DD}_{slug-da-decisao}.decision.md` |
| Débito | `{YYYY-MM-DD}_{slug-do-debito}.techdebt.md` |

---

## Fluxo de trabalho com o agente

```
Tarefa recebida
      ↓
Projeto novo ou projeto existente sem contexto importado?
  ├─ NOVO → ai/new-project.md
  │         (wizard: entrevista + preenche todos os arquivos de contexto)
  │
  ├─ EXISTENTE NAO IMPORTADO → ai/import-project.md
  │         (wizard: entrevista + consolida contexto de projeto em andamento)
  │
  └─ EXISTENTE JA IMPORTADO → ai/module-context-reader.md  ← SEMPRE, antes de qualquer ação
              (lê o código do módulo, gera resumo de contexto, confirma entendimento)
                    ↓
              core/plans.md
              (perguntas obrigatórias → gera .plan.md com status DRAFT)
                    ↓
              ai/approval-flow.md
              (aguarda aprovação humana → APPROVED)
                    ↓
              Execução com engineering/ + core/ ativos
                    ↓
              quality/code-review.md
              (gera .review.md → aguarda aprovação)
                    ↓
              Atualiza decision-log + tech-debt se necessário
```

Nenhuma ação destrutiva (delete, migration, alteração de contrato de API) avança sem aprovação explícita. O agente nunca age sobre um módulo sem antes ler e entender seu código.

Além disso, o agente nunca instala pacotes/dependências automaticamente: ele apenas sugere; o programador valida na fonte oficial e informa ao agente qual opção foi adotada.

---

## Como iniciar (novo ou importacao)

### 1. Projeto novo

1. Acione o fluxo `ai/new-project.md`
2. Responda os 5 blocos de perguntas
3. Defina os caminhos de artefatos (`.plan.md`, `.review.md`, `.decision.md`, `.techdebt.md`)
4. Confirme as regras inegociáveis de segurança e performance
5. Aprove o resumo final para o agente atualizar os arquivos de contexto

### 2. Projeto existente (importacao)

1. Acione o fluxo `ai/import-project.md`
2. Responda os blocos de mapeamento arquitetural e estado técnico atual
3. Defina riscos, requisitos de segurança/performance e fluxo de time
4. Defina os caminhos de artefatos compartilhados
5. Aprove o resumo final para consolidar o contexto antes de novas implementações

---

## Como evoluir essa estrutura com o tempo

### Princípios de evolução

1. **Adicione contexto, não ruído** — cada arquivo deve conter regras claras e acionáveis. Evite conteúdo genérico que o agente não pode aplicar concretamente.
2. **Registre o que o agente errou** — quando o agente tomar uma decisão errada, corrija o arquivo de contexto correspondente para evitar reincidência.
3. **Versione as decisões** — use `quality/decision-log.md` para rastrear por que uma regra foi adicionada ou alterada.
4. **Revise trimestralmente** — a cada ciclo do projeto, revise `core/patterns.md` e `engineering/` para remover regras obsoletas.

### Quando adicionar novos arquivos

| Situação | Onde adicionar |
|---|---|
| Nova convenção de código surgiu | `core/standards.md` ou `core/patterns.md` |
| O agente precisa de nova habilidade especializada | `ai/skills.md` ou novo arquivo em `ai/` |
| Novo padrão técnico de segurança | `engineering/security.md` |
| Nova categoria de débito técnico recorrente | `quality/tech-debt.md` |
| Novo tipo de risco identificado | `quality/risk-analysis.md` |

### Quando não adicionar novos arquivos

- Não crie arquivos para casos únicos — prefira atualizar o arquivo existente mais próximo
- Não duplique contexto entre arquivos — se uma regra já existe em `engineering/security.md`, não a repita em `ai/guardrails.md`
- Não adicione regras sem exemplo concreto — regras vagas são ignoradas pelo agente

---

## Referência rápida de arquivos por cenário

| Quero... | Consultar |
|---|---|
| Criar uma nova feature | `core/architecture.md`, `core/patterns.md` |
| Revisar um PR | `quality/code-review.md`, `engineering/validations.md` |
| Analisar segurança | `ai/security-blue-team.md`, `ai/security-red-team.md`, `engineering/security.md` |
| Registrar uma decisão técnica | `quality/decision-log.md` |
| Entender o que o agente pode/não pode fazer | `ai/guardrails.md`, `ai/agent-behavior.md` |
| Gerar documentação de um módulo | `ai/module-doc-generator.md` |
| Adicionar testes | `engineering/testing.md` |
| Identificar débito técnico | `quality/tech-debt.md` |
| Otimizar performance | `engineering/performance.md` |
| Criar tabela, migration, query, índice ou configurar cache/busca | `ai/dba.md` |
| Coletar dado pessoal, lidar com privacidade ou atender legislação (LGPD, GDPR...) | `ai/dpo.md` |

---

## Roteiros Prontos Para Chat

Use os textos abaixo como mensagem inicial no chat com o agente.

### Navegacao rapida

| Tipo | Arquivo |
|---|---|
| Fluxo de onboarding de projeto novo | `ai/new-project.md` |
| Fluxo de importacao de projeto existente | `ai/import-project.md` |
| Gatilhos por contexto de mensagem | `ai/triggers.md` |
| Referencias oficiais de bibliotecas | `ai/library-references.md` |
| Atalhos e prompt base | `ai/prompts.md` |
| Script pronto para chat (novo projeto) | `ai/chat-script-new-project.md` |
| Script pronto para chat (importacao) | `ai/chat-script-import-project.md` |

### Como funcionam os gatilhos

O roteamento inicial agora pode ser feito automaticamente pelo contexto da mensagem.

Prioridade de decisao:

1. Pedido explicito de agente especifico
2. Pedido de projeto novo
3. Pedido de importacao de projeto
4. Sem contexto claro: perguntar e, se necessario, cair em `ai/module-context-reader.md`

Exemplos de uso no chat:

- "Quero iniciar um projeto novo do zero" -> aciona `ai/new-project.md`
- "Quero importar um projeto que ja existe" -> aciona `ai/import-project.md`
- "Executar agente security-blue-team" -> aciona agente especificado

Arquivos dedicados para facilitar copia e uso pelo time:
- `ai/chat-script-new-project.md`
- `ai/chat-script-import-project.md`
- `ai/chat-script-library-references.md`
- Teste rapido de gatilhos: `ai/triggers.md` (secao "Bloco de teste rapido (10 frases)")

### Roteiro 1 - Onboarding de projeto novo

```text
Quero iniciar um projeto novo do zero.

Execute o fluxo ai/new-project.md e conduza a entrevista completa em blocos.

Regras obrigatorias:
1. Seguranca e performance sao inegociaveis
2. Nao pular perguntas obrigatorias
3. Nao sobrescrever sem minha confirmacao
4. Mostrar resumo ao final de cada bloco

No fim, quero:
1. Resumo final de todas as decisoes
2. Proposta de atualizacao dos arquivos de contexto
3. Registro da decisao inicial de setup
4. Lista de pendencias

Importante sobre dependencias:
Voce nao pode instalar pacotes/dependencias automaticamente.
Apenas sugira. Eu vou validar na pagina oficial, instalar manualmente e te avisar qual opcao foi adotada.
```

### Roteiro 2 - Importacao de projeto existente

```text
Quero importar um projeto ja em andamento para a estrutura de contexto.

Execute o fluxo ai/import-project.md e faca todas as perguntas obrigatorias para consolidar o contexto do projeto.

Objetivo:
1. Mapear arquitetura, stack e modulos
2. Mapear riscos tecnicos e de negocio
3. Definir regras de seguranca e performance (inegociaveis)
4. Definir caminhos de artefatos (.plan.md, .review.md, .decision.md, .techdebt.md)
5. Atualizar os arquivos de contexto para os demais agentes

No fim, quero:
1. Resumo de importacao para validacao
2. Lista do que foi atualizado
3. Lista de lacunas pendentes
4. Registro de decisao do onboarding de importacao

Importante sobre dependencias:
Voce nao pode instalar pacotes/dependencias automaticamente.
Apenas sugira. Eu vou validar na fonte oficial, instalar manualmente e te avisar o pacote final para voce seguir com a documentacao correta.
```

### Roteiro 3 - DBA Agent (banco de dados)

```text
Executar agente dba.

Contexto: [descreva brevemente o que precisa — ex: criar tabela de pacientes, otimizar query do módulo de agendamento, configurar índice no Elasticsearch]

Regras obrigatorias:
1. Analise pelos tres pilares: performance, integridade e seguranca
2. Apresente opcoes tecnicas com vantagens e desvantagens antes de qualquer implementacao
3. Nao execute nada sem minha aprovacao explicita
4. Se a opcao escolhida nao for a recomendada, registre o risco formalmente
```

### Roteiro 4 - DPO Agent (protecao de dados e privacidade)

```text
Executar agente dpo.

Contexto: [descreva brevemente o que precisa — ex: implementar cadastro de pacientes, integrar com servico de pagamento, configurar logs do sistema]

Regras obrigatorias:
1. Se for a primeira vez, conduza a configuracao de legislacoes antes de qualquer analise
2. Mapeie todos os dados pessoais envolvidos e classifique cada um
3. Para cada orientacao, aguarde meu posicionamento explicito: [ACEITO] ou [NAO ACEITO] + plano de mitigacao
4. Registre log completo da sessao (aceites e rejeicoes) no modulo afetado
5. Seguranca de dados e inegociavel — nao avance em itens criticos sem resolucao
```
