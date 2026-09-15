# Auto Improvements — sugestões proativas do agente

> **Quando carregar:** ao concluir uma tarefa, antes de escrever o `.review.md`.

O agente vê o código de perto e repetidamente — está numa boa posição para
notar o que merece melhorar. Está numa posição péssima para decidir sozinho o
que vale o custo. Este arquivo separa as duas coisas.

**Regra mãe: sugerir é sempre permitido. Executar fora do escopo, nunca.**

---

## O que o agente propõe sem perguntar

Melhorias **dentro** do que a tarefa já toca, que não mudam comportamento e
cabem no mesmo commit:

- Tipo faltando em assinatura que já está sendo alterada
- Constante nomeada no lugar de valor mágico que apareceu no diff
- Retorno cedo no lugar de aninhamento que ele mesmo criaria
- Docblock explicando o *porquê* de uma decisão não óbvia
- Teste de borda óbvio ausente para o código novo
- Import morto deixado pela própria mudança

**R-AIM-01 — Isto não é permissão para arrumar o arquivo.**
É permissão para não deixar o próprio rastro sujo.

---

## O que o agente sugere e NÃO executa

Tudo que sai do escopo. A sugestão vai para o `.review.md`, e a decisão é
humana:

| Categoria | Exemplos |
|---|---|
| Arquitetura | regra em controller, módulo acoplado, classe com papéis demais |
| Performance | N+1 em outro arquivo, listagem sem paginação, falta de índice |
| Segurança | entrada sem validação, autorização ausente, segredo no código |
| Testes | módulo crítico descoberto, teste frágil, cobertura em queda |
| Observabilidade | caminho crítico sem log, erro engolido |
| Duplicação | terceira cópia da mesma regra |
| Dependência | pacote sem atualização há anos, CVE conhecida |
| Dado pessoal | campo sensível sem tratamento (`ai/dpo.md`) |

**R-AIM-02 — Sugestão de segurança, de dado pessoal ou de perda de dado é
escalada na hora, não guardada para o fim.**

---

## Como uma sugestão é escrita

**R-AIM-03 — Toda sugestão tem cinco partes.** Sem elas é ruído.

1. **O que** — o fato observado, com arquivo e linha
2. **Por que importa** — o custo concreto, não "boa prática"
3. **Evidência** — número, ocorrência, erro real
4. **Proposta** — a mudança específica
5. **Custo** — esforço e risco estimados

```markdown
### [Performance] N+1 em InvoiceListController::index

**O quê:** `app/Http/Controllers/InvoiceListController.php:42` — o laço acessa
`$invoice->customer` sem eager loading.
**Por que importa:** 1 + N queries por listagem; com `per_page=100`, 101
consultas por request na tela mais acessada do sistema.
**Evidência:** medido em staging — 340 ms, 112 queries.
**Proposta:** `->with('customer')` no repositório, `R-PER-01`.
**Custo:** 1 linha, baixo risco, coberto pelo teste de listagem existente.
```

**R-AIM-04 — Sem número, não é evidência.**
"Parece lento" não prioriza nada.

**R-AIM-05 — Sem custo estimado, não é decidível.**
Quem decide precisa comparar esforço com benefício.

---

## Limites

**R-AIM-06 — Máximo de 5 sugestões por revisão.**
Uma lista de 30 itens não é lida. Traga as 5 de maior relação
impacto/esforço e registre o resto como débito.

**R-AIM-07 — Não sugira o que contraria o padrão do projeto.**
Se o módulo é consistente e diferente desta base, a divergência é decisão
local, não defeito (`core/patterns.md`).

**R-AIM-08 — Não repita sugestão recusada.**
Recusa vira nota em `quality/decision-log.md` e não volta na próxima tarefa. O
agente insistir no que já foi decidido queima a atenção do humano para o que
importa.

**R-AIM-09 — Não sugira reescrita como primeira opção.**
"Reescrever o módulo" quase nunca é a melhor relação custo/benefício, e nunca
é uma sugestão — é um projeto.

**R-AIM-10 — Não sugira adicionar dependência.**
Isso é guardrail (`ai/guardrails.md`, item 5): proponha a capacidade, o humano
escolhe o pacote e valida na fonte oficial.

---

## Destino

- **Aceita e no escopo** → executa nesta tarefa
- **Aceita e fora do escopo** → vira tarefa própria, com plano próprio
- **Aceita mas adiada** → `quality/tech-debt.md`, com prioridade
- **Recusada** → `quality/decision-log.md`, com o motivo, para não voltar

---

## Referências

- Revisão: `quality/code-review.md`
- Débito: `quality/tech-debt.md`
- Decisões: `quality/decision-log.md`
- Limites de refatoração: `engineering/refactoring.md`
