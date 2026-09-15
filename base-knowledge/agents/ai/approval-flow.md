# Approval Flow — DRAFT → APPROVED → EXECUTION

> **Quando carregar:** sempre que uma tarefa envolver escrita de código,
> mudança de schema, alteração de contrato ou qualquer item de
> `ai/guardrails.md`.

O fluxo existe para uma coisa: **nenhuma mudança irreversível acontece sem um
humano ter visto o que ia acontecer.** Tudo abaixo serve a isso.

---

## Os três estados

```
   DRAFT ──(humano aprova)──▶ APPROVED ──(agente executa)──▶ EXECUTION
     ▲                                                          │
     └──────────────(escopo mudou / falhou)─────────────────────┘
```

### DRAFT

O agente propõe. Nada é escrito fora do arquivo de plano.

**R-APR-01 — Todo DRAFT declara seis coisas:**

1. **Objetivo** — em uma frase, o resultado esperado.
2. **Arquivos tocados** — lista explícita, com criado/alterado/removido.
3. **Efeitos irreversíveis** — migration, deleção, mudança de contrato,
   chamada externa. Se não há nenhum, diga "nenhum".
4. **Riscos** — o que pode quebrar, e como saber que quebrou
   (`quality/risk-analysis.md`).
5. **Testes** — o que vai provar que funcionou.
6. **Rollback** — como desfazer. "Não tem" é resposta válida, mas precisa
   estar escrita.

**R-APR-02 — Sem plano, sem código.**
Não existe "pequeno demais para planejar" em mudança que toca schema,
contrato, produção ou dependência. Para o resto, o plano pode ser curto — mas
existe.

**R-APR-03 — O DRAFT vai para arquivo, não só para o chat.**
`{YYYY-MM-DD}_{slug-da-tarefa}.plan.md`, no caminho definido pelo Tech Lead
(ver `core/plans.md`). Chat se perde; arquivo é revisável e versionável.

**R-APR-04 — Incerteza vira pergunta, não suposição.**
Se o agente precisou escolher entre duas leituras do pedido, o DRAFT registra
a escolha e o porquê — em destaque, para o humano poder discordar barato.

### APPROVED

**R-APR-05 — Aprovação é explícita, específica e humana.**
"Pode seguir", "aprovado", "manda ver" referidos AO PLANO. Silêncio não é
aprovação. Uma mensagem antiga não é aprovação. Ausência de objeção não é
aprovação.

**R-APR-06 — Aprovação vale para o plano aprovado, e só.**
Aprovar o plano A não aprova o item que apareceu no meio do caminho.

**R-APR-07 — Aprovação parcial é possível e deve ser respeitada.**
"Aprovo os passos 1 a 3, o 4 a gente discute" significa: execute 1 a 3, pare,
volte a DRAFT para o 4.

**R-APR-08 — O agente registra quem aprovou e quando.**
No próprio `.plan.md`: `Aprovado por @usuario em 2026-03-14`.

### EXECUTION

**R-APR-09 — Executa o que está no plano. Nada além.**
Achou outro problema no caminho? Registra em `quality/tech-debt.md` e segue.
Corrigir de passagem contamina a revisão e torna o rollback impossível.

**R-APR-10 — Escopo que muda volta para DRAFT.**
Se durante a execução ficar claro que o plano estava errado, o agente PARA,
diz o que descobriu e propõe o plano revisado. Não improvisa.

**R-APR-11 — Falha para o fluxo.**
Teste vermelho, migration recusada, dependência ausente: parar e relatar vale
mais que seguir e deixar meia mudança aplicada.

**R-APR-12 — Toda execução termina em revisão.**
`.review.md` conforme `quality/code-review.md`, mesmo quando deu tudo certo —
principalmente quando deu tudo certo.

---

## Quando o fluxo é obrigatório

| Situação | DRAFT obrigatório |
|---|---|
| Migration ou alteração de schema | **sim** |
| Mudança em contrato de API (rota, payload, status) | **sim** |
| Qualquer ação em produção | **sim** |
| Instalar ou atualizar dependência | **sim** |
| Remover arquivo, tabela, coluna ou endpoint | **sim** |
| Alterar regra de autenticação, autorização ou dado pessoal | **sim** |
| Refatoração que atravessa módulos | **sim** |
| Feature nova dentro de um módulo | sim (pode ser curto) |
| Corrigir bug localizado com teste que o reproduz | plano curto |
| Ajuste de texto, comentário, formatação | não |

Na dúvida entre duas linhas da tabela, vale a mais restritiva.

---

## Relação com os guardrails

`ai/guardrails.md` lista o que o agente **nunca** faz sozinho. Este arquivo
descreve **como** o "sozinho" deixa de valer: passando por DRAFT e recebendo
aprovação explícita. Guardrail acionado sem aprovação = parada imediata, não
uma pergunta retórica seguida de execução.

---

## Referências

- Bloqueios: `ai/guardrails.md`
- Fluxo geral de 6 passos: `ai/agent-behavior.md`
- Estrutura do plano: `core/plans.md`
- Revisão pós-execução: `quality/code-review.md`
- Registro de decisão: `quality/decision-log.md`
