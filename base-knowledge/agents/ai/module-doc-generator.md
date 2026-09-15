# Module Documentation Agent — documentação por módulo

> **Aciona quando:** um módulo é criado, sua fronteira muda (rota, evento,
> contrato, schema), ou por pedido explícito.
> **Destino:** `modules/{modulo}/docs/`, ou o caminho definido pelo Tech Lead.

O alvo desta documentação são duas leitoras: a pessoa que entra no módulo
amanhã e o **agente**, que precisa responder sobre o módulo sem reler todo o
código. Por isso ela é curta, factual e estruturada — não é um texto de
apresentação.

---

## Regras

**R-DOC-01 — Documentação é derivada do código, não paralela a ele.**
Toda afirmação sai de um arquivo real. Se não dá para apontar onde, não entra.

**R-DOC-02 — Documente a FRONTEIRA, não o interior.**
O que o módulo oferece, o que consome, que invariantes mantém. Detalhe interno
muda toda semana e a documentação vira mentira. O código já mostra o interior.

**R-DOC-03 — Nada de segredo, nada de dado real.**
Exemplos usam valores fictícios evidentes. Nenhuma URL interna, credencial,
IP ou nome de pessoa.

**R-DOC-04 — Documentação desatualizada é pior que ausente.**
Ausente faz a pessoa ler o código. Errada faz ela confiar. Se não vai ser
mantida, não gere.

**R-DOC-05 — Regenerar preserva o que foi escrito à mão.**
Seções marcadas como manuais não são sobrescritas. O agente atualiza o gerado
e relata o que ficou divergente.

**R-DOC-06 — O que o agente não conseguiu determinar aparece como pendência.**
`> **Pendente:** origem do campo X não identificada.` Inventar é pior que
admitir o buraco — e o buraco vira tarefa.

---

## Estrutura

````markdown
# Módulo: Invoicing

> Gerado por `ai/module-doc-generator.md` em 2026-03-14 · commit `a3f91c2`

## Propósito
Uma frase. O que deixa de funcionar se este módulo sumir.

## Fronteira

### Oferece
| Tipo | Nome | Onde |
|---|---|---|
| HTTP | `POST /api/invoices` | `Http/Controllers/InvoiceController@store` |
| Evento | `InvoicePaid` | `Events/InvoicePaid.php` |
| Service | `TaxCalculator::calculate()` | `Services/TaxCalculator.php` |

### Consome
| Tipo | Nome | De onde |
|---|---|---|
| Service | `CustomerLookup` | módulo `customers` |
| Evento | `PaymentConfirmed` | módulo `payments` |
| Externo | API do gateway | `Integrations/StripeGateway.php` |

## Modelo de dados
| Tabela | Papel | Relações |
|---|---|---|
| `invoices` | documento fiscal | `1:N invoice_items`, `N:1 customers` |

## Fluxos principais
### Emissão
1. `IssueInvoiceAction` valida o pedido
2. `TaxCalculator` aplica o regime do cliente
3. Persiste em transação
4. Emite `InvoiceIssued` **após** o commit (`R-ARC-17`)

## Invariantes
- Fatura emitida não muda de valor; correção gera nota de ajuste
- `total` é sempre a soma dos itens mais impostos
- Valores em centavos, inteiros (`R-VAL-12`)

## Configuração
| Chave | Efeito | Default |
|---|---|---|
| `invoicing.due_days` | prazo de vencimento | 30 |

## Decisões
- Cálculo fiscal próprio em vez de biblioteca externa — ver
  `2025-11-02_calculo-fiscal.decision.md`

## Riscos e débitos conhecidos
- `quality/tech-debt.md`: retentativa do gateway não é idempotente

## Testes
`Tests/` — 34 testes. Cobertura de `Services/`: 94%.
````

---

## Fora do escopo

- Tutorial de uso da aplicação
- Explicação de framework
- Diagrama que ninguém vai atualizar
- Descrição método a método — para isso existe o código, e o RAG indexa

---

## Integração com o RAG

**R-DOC-07 — A seção "Fronteira" é a mais valiosa das duas leitoras.**
É dela que sai a resposta para "quem depende de quem" sem varrer o
repositório. Mantenha-a exata mesmo quando o resto envelhecer.

**R-DOC-08 — Cabeçalho com data e commit.**
É como o agente sabe que a documentação está atrás do código e avisa em vez de
responder com confiança sobre algo obsoleto.

---

## Referências

- Leitura do módulo: `ai/module-context-reader.md`
- Arquitetura e fronteiras: `core/architecture.md`
- Decisões: `quality/decision-log.md`
- Débitos: `quality/tech-debt.md`
