# Risk Analysis — análise de risco de mudanças

> **Quando carregar:** em todo DRAFT (`ai/approval-flow.md`, item 4) e antes de
> qualquer mudança que toque schema, contrato, produção ou dado pessoal.

Análise de risco não é formulário. É responder três perguntas:
**o que pode dar errado, como eu saberia, e o que eu faço então.**
Um risco sem detecção e sem plano é um susto agendado.

---

## Classificação

**R-RSK-01 — Risco = impacto × probabilidade, e ambos são declarados.**

| Impacto | Significa |
|---|---|
| **Crítico** | perda de dado, vazamento, sistema fora, dinheiro errado |
| **Alto** | fluxo principal quebrado, usuário bloqueado |
| **Médio** | fluxo secundário degradado, contorno existe |
| **Baixo** | cosmético, sem efeito funcional |

| Probabilidade | Significa |
|---|---|
| **Alta** | acontece no primeiro uso real |
| **Média** | acontece sob condição comum (concorrência, volume) |
| **Baixa** | exige combinação improvável |

**R-RSK-02 — Crítico × qualquer probabilidade exige aprovação explícita e
plano de rollback escrito.** Sem exceção.

---

## Gatilhos automáticos

Se a mudança contém qualquer item abaixo, a análise é obrigatória e detalhada:

- Migration — principalmente `DROP`, `ALTER` de coluna em uso, `NOT NULL` em
  tabela populada
- Mudança em contrato de API consumido por terceiro
- Alteração em autenticação, autorização ou sessão
- Qualquer coisa que toque dado pessoal (`ai/dpo.md`)
- Deleção de dado, arquivo, tabela ou endpoint
- Mudança em cobrança, preço, imposto ou cálculo financeiro
- Troca ou atualização maior de dependência
- Alteração em job recorrente ou em consumidor de fila
- Mudança que só se manifesta sob concorrência ou volume

---

## As perguntas

**R-RSK-03 — Quem depende disto?**
Outros módulos, front, app, parceiro, relatório, integração. Se a resposta é
"não sei", descobrir faz parte da análise — é onde o RAGX ajuda: busque quem
referencia o símbolo antes de assumir que nada depende.

**R-RSK-04 — E se rodar duas vezes?**
Job, webhook e retry chegam repetidos. A mudança aguenta?

**R-RSK-05 — E com 100× o volume?**
O que é instantâneo com 10 linhas pode travar com 10 milhões. Migration em
tabela grande trava escrita.

**R-RSK-06 — E se falhar no meio?**
Metade aplicada é pior que nada aplicado. Há transação? Há como retomar?

**R-RSK-07 — E o dado que já existe?**
Código novo costuma pressupor formato novo. Registro antigo, nulo, órfão ou
inconsistente continua lá.

**R-RSK-08 — Como eu descubro que quebrou?**
Alerta, métrica, log, reclamação de usuário. Se a resposta é a última, falta
instrumentação (`quality/observability.md`).

**R-RSK-09 — Como eu volto atrás?**
Reverter o commit basta? A migration tem `down` testado? Se o rollback é
impossível — migration destrutiva, e-mail enviado, webhook disparado — isso
precisa estar escrito em letras grandes no DRAFT.

---

## Mitigações que funcionam

**R-RSK-10 — Migration destrutiva vira duas etapas.**
Adicionar → migrar dado → passar a usar o novo → só depois remover o antigo,
em release separada. `DROP COLUMN` no mesmo deploy da mudança de código é como
se perde dado.

**R-RSK-11 — Contrato quebra em versão, não em silêncio.**
Campo novo é opcional. Campo removido é depreciado antes, com prazo e aviso a
quem consome.

**R-RSK-12 — Mudança arriscada entra atrás de feature flag.**
Desligar é mais rápido que reverter e fazer deploy.

**R-RSK-13 — Backup verificado ANTES da migration.**
Backup não testado é esperança, não mitigação.

**R-RSK-14 — Rollout gradual quando o volume é o risco.**

---

## Formato no plano

```markdown
## Riscos

| # | Risco | Impacto | Prob. | Detecção | Mitigação |
|---|---|---|---|---|---|
| 1 | `invoices.legacy_id` tem 1.2M linhas; NOT NULL trava escrita | Crítico | Alta | — | duas etapas: coluna nullable agora, backfill em job, NOT NULL na próxima release |
| 2 | Front v1 ainda lê `total` no topo do payload | Alto | Média | erro 500 no app; alerta de taxa de erro | manter `total` por 2 releases, marcado como depreciado |

**Rollback:** reverter commit + `php artisan migrate:rollback --step=1`
(testado em staging em 2026-03-12).
**Irreversível:** nenhum.
```

**R-RSK-15 — "Sem riscos identificados" é uma resposta possível — para mudança
que não toca nenhum gatilho.** Escrever isso sobre uma migration é sinal de que
a análise não foi feita.

---

## Depois

**R-RSK-16 — Risco que se materializou vira registro.**
`quality/decision-log.md` se mudou a decisão; `quality/tech-debt.md` se ficou
pendência. Análise que ninguém revisita não melhora a próxima.

---

## Referências

- Fluxo de aprovação: `ai/approval-flow.md`
- Guardrails: `ai/guardrails.md`
- Detecção: `quality/observability.md`
- Banco e migrations: `ai/dba.md`
- Dados pessoais: `ai/dpo.md`
