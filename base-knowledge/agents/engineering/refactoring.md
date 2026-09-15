# Refactoring — limites da refatoração automática

> **Quando carregar:** ao propor ou executar mudança de forma sem mudança de
> comportamento.

Definição operacional, e ela é rígida: **refatoração não muda comportamento
observável.** Se a saída, o contrato, o schema ou o efeito colateral mudam,
não é refatoração — é mudança, e vale `ai/approval-flow.md` por inteiro.

---

## Pré-requisitos

**R-REF-01 — Sem teste cobrindo, não se refatora.**
Primeiro escreva o teste que caracteriza o comportamento atual. Ele é a única
prova de que a forma mudou e o resultado não.

**R-REF-02 — Refatoração vem em commit separado.**
Nunca junto da feature. Misturar impede revisar e impede reverter só uma das
duas (`A-PAT-15`).

**R-REF-03 — Um tipo de mudança por commit.**
Renomear, extrair e mover em commits distintos. Diff que faz três coisas não é
revisável.

**R-REF-04 — A suíte passa antes e depois, sem alteração nos testes.**
Se o teste precisou mudar, o comportamento mudou. Volte ao passo anterior.

---

## Escopo permitido sem aprovação

Só isto, e apenas dentro do arquivo ou módulo que a tarefa já toca:

- Renomear variável, parâmetro ou método **privado**
- Extrair método privado a partir de bloco repetido ou longo
- Substituir número/string mágico por constante nomeada
- Inverter condicional para retorno cedo (`R-PAT-04`)
- Remover código morto e import não usado
- Remover duplicação literal dentro do mesmo arquivo
- Adicionar tipo faltante em assinatura já existente
- Aplicar o formatador

**R-REF-05 — "Dentro do arquivo que a tarefa já toca" é literal.**
Melhorar um arquivo vizinho "já que estou aqui" é escopo novo.

---

## Exige aprovação explícita

- Renomear qualquer coisa **pública**: classe, método público, rota, evento,
  coluna, chave de config
- Mover arquivo entre módulos ou camadas
- Extrair ou fundir classe
- Trocar assinatura de método usado fora do arquivo
- Alterar hierarquia de herança ou interface
- Mudar estrutura de pastas
- Trocar biblioteca, mesmo por equivalente
- Qualquer mudança em migration, seeder ou schema
- Refatoração que atravessa mais de um módulo

**R-REF-06 — Na dúvida sobre qual lista se aplica, vale a segunda.**

---

## Nunca, mesmo com aprovação genérica

**R-REF-07 — Não refatore código sem teste "aproveitando o embalo".**
Escreva o teste primeiro, e isso é uma tarefa com plano próprio.

**R-REF-08 — Não reescreva um módulo inteiro dentro de uma tarefa de feature.**
Reescrita é projeto, tem plano, tem risco analisado
(`quality/risk-analysis.md`).

**R-REF-09 — Não "modernize" sintaxe em arquivo que a tarefa não toca.**
Cem arquivos reformatados escondem a mudança de uma linha que importa.

**R-REF-10 — Não mude o padrão local para o padrão desta base.**
Se o módulo é consistente consigo mesmo, ele está certo (`R-PAT` — "como o
agente aplica"). Divergência vira nota em `quality/decision-log.md`.

---

## Como reportar

**R-REF-11 — Todo commit de refatoração declara três coisas:**

1. O que mudou de forma
2. Por que valeu a pena — legibilidade, duplicação removida, acoplamento
   quebrado
3. A prova de que o comportamento não mudou: a suíte, inalterada, passando

Exemplo:

```
refactor(invoicing): extrai TaxCalculator de IssueInvoiceAction

A action acumulava 140 linhas de cálculo fiscal misturadas com orquestração.
Cálculo agora é um service testável isoladamente (R-ARC-06).

Comportamento inalterado: 34 testes de invoicing passando sem edição.
```

---

## Quando NÃO refatorar

- Código que vai ser removido nas próximas semanas
- Módulo em processo de substituição
- Véspera de entrega crítica — risco não compensa
- Código feio mas estável, coberto e que ninguém toca há um ano: registre como
  débito de prioridade baixa e siga

**R-REF-12 — "Está feio" não é justificativa suficiente.**
A justificativa é o custo que a forma atual impõe: bug recorrente, tempo de
entendimento, impossibilidade de testar.

---

## Referências

- Padrões e anti-patterns: `core/patterns.md`
- Fluxo de aprovação: `ai/approval-flow.md`
- Testes de caracterização: `engineering/testing.md`
- Registro de débito: `quality/tech-debt.md`
