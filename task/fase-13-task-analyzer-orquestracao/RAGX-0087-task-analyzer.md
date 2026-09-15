# RAGX-0087 — Task Analyzer — classificação por sinais

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0086`, `RAGX-0028` |
| **Bloqueia** | `RAGX-0088`, `RAGX-0089` |
| **Documentação** | [20-task-analyzer.md](../../docs/20-task-analyzer.md) |
| **Status** | `todo` |

## Objetivo

Classificar toda solicitação e decidir entre executar agora e documentar antes — por critério objetivo, auditável e offline.

## Entregáveis

- [ ] `signals.yaml` declarativo, no mesmo idioma de `intents.yaml` (Context Engine)
- [ ] Os 7 scores: complexity, architecture, business_rule, dependency, risk, security, documentation
- [ ] `dependency` e `documentation` MEDIDOS NO ÍNDICE (search + graph), não só por léxico
- [ ] Sinais de REDUÇÃO (typo, renomear, ajustar mensagem) que derrubam o score
- [ ] Portas rígidas: `security >= 40` nunca é DIRECT_EXECUTION; `risk >= 60` exige aprovação
- [ ] `reasoning_summary` montado a partir dos sinais disparados
- [ ] Sobreposição pelo agente, com justificativa registrada

## Fora de escopo

- Chamada a LLM — o RAGX não tem um (ADR-0015)
- Expor chain-of-thought: `reasoning_summary` é justificativa operacional curta

## Critérios de aceite

- [ ] Typo classifica como DIRECT_EXECUTION mesmo contendo a palavra 'módulo'
- [ ] 'Implementar módulo de telemedicina' classifica como DOCUMENTATION_REQUIRED + DECOMPOSITION
- [ ] Mudança em autenticação NUNCA sai como DIRECT_EXECUTION
- [ ] A mesma frase pontua mais alto num repositório onde o assunto já aparece em vários módulos
- [ ] Classificação é determinística: mesma entrada, mesma saída
- [ ] `ragx task analyze` não escreve nada

## Testes

- [ ] Tabela de casos: 12 solicitações reais → classificação esperada
- [ ] Sinal de redução vence sinal de aumento quando o pedido é trivial
- [ ] Porta de segurança: frases de autenticação, nenhuma vira DIRECT_EXECUTION
- [ ] Determinismo: execuções repetidas, mesma saída

## Notas

A limitação honesta: o classificador lê palavras e mede impacto; não entende o pedido. Um pedido escrito de forma incomum pode ser subestimado — por isso a sobreposição existe e fica registrada.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
