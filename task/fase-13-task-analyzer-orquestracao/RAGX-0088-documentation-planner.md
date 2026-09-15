# RAGX-0088 — Documentation Planner

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0087`, `RAGX-0043` |
| **Bloqueia** | `RAGX-0089` |
| **Documentação** | [20-task-analyzer.md](../../docs/20-task-analyzer.md) |
| **Status** | `todo` |

## Objetivo

Decidir QUAIS documentos são necessários e produzi-los já fundamentados no conhecimento existente — nunca isolados dele.

## Entregáveis

- [ ] `doctypes.yaml`: 15 tipos, seções obrigatórias e dependência entre tipos
- [ ] Coleta de contexto: search + graph + dictionary + decisions + tarefas anteriores
- [ ] Esqueleto por tipo, com as referências encontradas já dentro
- [ ] Lacuna marcada como `> **Pendente:** ...` explícito
- [ ] Ordem topológica entre tipos (architecture antes de technical, technical antes de database)
- [ ] Destino `knowledge/<tipo>/`, versionado

## Fora de escopo

- Escrever o texto do documento — isso é tarefa do agente
- Gerar documento sem nenhuma fundamentação no índice

## Critérios de aceite

- [ ] Nenhum documento é gerado sem ao menos uma referência ao conhecimento existente, ou uma pendência explícita
- [ ] Documento gerado passa pelo Security Gate como qualquer entrada
- [ ] Regenerar sem mudança produz arquivo byte-idêntico
- [ ] Tipos respeitam a ordem de dependência declarada

## Testes

- [ ] Planner em projeto vazio produz pendências, não texto inventado
- [ ] Documento com segredo é BLOQUEADO na indexação
- [ ] Ordem topológica respeitada com os 15 tipos

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
