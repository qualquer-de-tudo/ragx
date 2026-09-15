# Agent Behavior

Este arquivo define o **fluxo geral de comportamento do agente** para qualquer tarefa recebida. Todo agente deve seguir este fluxo, com aprovação obrigatória antes de qualquer execução.

---

## Fluxo principal

```
TAREFA RECEBIDA
      ↓
Projeto novo ou projeto existente sem contexto importado?
  → NOVO: executar ai/new-project.md (setup wizard)
  → EXISTENTE NAO IMPORTADO: executar ai/import-project.md
  → EXISTENTE JA IMPORTADO: continuar abaixo
      ↓
PASSO 1 — Leitura de contexto (OBRIGATÓRIO)
  Executar: ai/module-context-reader.md
  → Analisar o código do módulo afetado
  → Gerar resumo de contexto
  → Confirmar entendimento com o programador
      ↓
PASSO 2 — Planejamento (OBRIGATÓRIO)
  Executar: core/plans.md
  → Fazer perguntas obrigatórias de escopo, riscos e critérios de aceite
  → Gerar arquivo .plan.md com status DRAFT
  → Aguardar aprovação humana
      ↓
PASSO 3 — Aprovação (OBRIGATÓRIO)
  Executar: ai/approval-flow.md
  → Status muda de DRAFT para APPROVED
  → Sem aprovação: agente não avança
      ↓
PASSO 4 — Execução
  → Aplicar regras de: core/architecture.md, core/patterns.md, core/standards.md
  → Aplicar regras de: engineering/ (security, testing, validations, performance)
  → Consultar ai/guardrails.md para confirmar que nenhum bloqueio está sendo violado
      ↓
PASSO 5 — Revisão pós-execução (OBRIGATÓRIO)
  Executar: quality/code-review.md
  → Gerar arquivo .review.md
  → Aguardar aprovação humana
      ↓
PASSO 6 — Registro (OBRIGATÓRIO)
  → Atualizar quality/decision-log.md se decisão técnica foi tomada
  → Atualizar quality/tech-debt.md se débito foi introduzido
  → Atualizar status do .plan.md para DONE
```

---

## Regras gerais de comportamento

1. **Nunca pular o Passo 1** — o agente não pode agir sobre um módulo sem antes entender seu código
2. **Nunca pular o Passo 2** — nenhum código é gerado sem plano aprovado
3. **Nunca pular a aprovação** — o agente aguarda ativamente a confirmação humana; não assume que silence = aprovação
4. **Questionar antes de assumir** — se houver ambiguidade, o agente pergunta; não interpreta por conta própria
5. **Escopo restrito** — o agente não realiza ações fora do escopo aprovado no plano, mesmo que identifique melhorias
6. **Transparência total** — o agente sempre explica o que está prestes a fazer antes de fazer

---

## Ações que sempre exigem aprovação humana explícita

- Deletar ou mover arquivos
- Alterar schema de banco de dados
- Alterar contrato de API (endpoints, payloads)
- Alterar arquivos de configuração de ambiente
- Instalar pacotes, dependencias, bibliotecas ou plugins
- Qualquer ação com efeito em produção
- Registrar um débito de prioridade CRÍTICA

---

## Referência de agentes especializados

| Situação | Agente a invocar |
|---|---|
| Projeto novo sem código | `ai/new-project.md` |
| Projeto existente sem contexto importado | `ai/import-project.md` |
| Analisar módulo existente | `ai/module-context-reader.md` |
| Análise de vulnerabilidade (defesa) | `ai/security-blue-team.md` |
| Simulação de ataque (ofensivo) | `ai/security-red-team.md` |
| Gerar documentação de módulo | `ai/module-doc-generator.md` |
| Banco de dados, schema, queries, cache ou busca | `ai/dba.md` |
| Proteção de dados, privacidade e legislação (LGPD, GDPR...) | `ai/dpo.md` |
