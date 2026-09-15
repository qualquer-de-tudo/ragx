# Standards — convenções de código

> **Quando carregar:** antes de escrever ou revisar qualquer linha de código.
> **Precedência:** o código existente do módulo ganha desta página. Se o módulo
> contraria uma regra daqui de forma consistente, isso é um padrão local —
> registre em `quality/decision-log.md`, não "corrija" de passagem.

Cada regra tem ID estável (`R-STD-nn`). Cite o ID em review, plano e débito:
é o que torna a regra rastreável e pesquisável.

---

## Tipagem

**R-STD-01 — Tipagem estrita ligada em todo arquivo novo.**
PHP: `declare(strict_types=1);` na primeira linha, sempre.
TypeScript: `strict: true`; `any` só com comentário justificando e prazo.
Python: anotação em toda assinatura pública.

**R-STD-02 — Todo parâmetro e todo retorno são tipados.**
Inclui `void`, `never` e `null`. `mixed` é confissão de que o desenho está
indefinido: resolva o desenho, não a assinatura.

**R-STD-03 — Coleção tipada declara o que contém.**
`array` sozinho não diz nada. Use `@param User[] $users`, `list<User>`,
`List[User]` — o que a stack oferecer. Se a linguagem não expressa, o docblock
expressa.

**R-STD-04 — Nulo é decisão, não descuido.**
Um retorno `?Foo` obriga quem chama a tratar ausência. Se ausência é erro,
lance exceção em vez de devolver `null`.

---

## Nomenclatura

**R-STD-05 — O nome diz o que é, não como foi feito.**
`UserRepository`, não `UserSqlHelper`. `calculateInvoiceTotal`, não
`doCalc2`. Nome que precisa de comentário para ser entendido é nome errado.

**R-STD-06 — Convenção por tipo de símbolo.**

| Símbolo | Padrão | Exemplo |
|---|---|---|
| Classe, interface, enum | `PascalCase` | `InvoiceService` |
| Método, função, variável | `camelCase` (PHP/TS) · `snake_case` (Python) | `sendInvoice` |
| Constante | `UPPER_SNAKE_CASE` | `MAX_RETRY_ATTEMPTS` |
| Arquivo de classe | igual ao nome da classe | `InvoiceService.php` |
| Tabela de banco | plural, `snake_case` | `invoice_items` |
| Coluna | singular, `snake_case` | `created_at` |
| Rota HTTP | `kebab-case`, plural | `/api/invoice-items` |
| Evento | passado, `PascalCase` | `InvoicePaid` |
| Branch | `tipo/slug-curto` | `feat/invoice-pdf` |

**R-STD-07 — Booleano pergunta.**
`isActive`, `hasPermission`, `shouldRetry`. Nunca `status`, `flag`, `check`.

**R-STD-08 — Sem abreviação inventada.**
`repository`, não `repo`. `calculate`, não `calc`. Exceções consagradas na
indústria (`id`, `url`, `http`, `db`) valem; as suas, não.

---

## Formatação

**R-STD-09 — O formatador decide, não a pessoa.**
PHP: PSR-12 via Pint ou PHP-CS-Fixer. TS: Prettier. Python: Ruff format.
Discussão sobre formatação em review é tempo perdido — configure a ferramenta.

**R-STD-10 — Linha de até 120 colunas.**
Acima disso, o problema raramente é a linha: é a expressão que faz coisas
demais.

**R-STD-11 — Uma classe por arquivo. Um conceito por classe.**

---

## Documentação no código

**R-STD-12 — Docblock existe para o que o tipo não diz.**
Assinatura já tipada não precisa de `@param string $name Nome`. Precisa de:
o que a função faz, o que ela pressupõe, o que ela lança, e *por que* alguma
decisão não óbvia foi tomada.

```php
/**
 * Concilia o extrato com os lançamentos do período.
 *
 * Usa o valor BRUTO porque a taxa da adquirente chega em arquivo separado,
 * dias depois — conciliar pelo líquido produziria divergência permanente.
 *
 * @throws PeriodNotClosedException quando o período ainda aceita lançamentos
 */
```

**R-STD-13 — Comentário explica o porquê; o código já mostra o quê.**
`// incrementa i` é ruído. `// a API devolve 200 com corpo de erro — daí a
checagem dupla` é conhecimento que se perderia.

**R-STD-14 — Comentário mentiroso é pior que comentário ausente.**
Mudou o código, mudou o comentário. No mesmo commit.

**R-STD-15 — `TODO` sem dono e sem data é lixo.**
Formato: `// TODO(@usuario, 2026-03-01): <o quê>`. Sem os três campos, vira
débito registrado (`quality/tech-debt.md`) ou não existe.

---

## Estrutura de arquivo

**R-STD-16 — Ordem previsível dentro da classe.**
Constantes → propriedades → construtor → métodos públicos → métodos
protegidos → métodos privados. Quem lê encontra sem procurar.

**R-STD-17 — Imports organizados e sem sobras.**
Agrupados (stdlib, terceiros, projeto), ordenados, sem import não usado.
O formatador resolve; o agente não deixa passar.

**R-STD-18 — Sem código morto.**
Bloco comentado "para o caso de precisar" é o que o Git já guarda. Apague.

---

## Erros

**R-STD-19 — Exceção específica, nunca genérica.**
`InvoiceNotFoundException`, não `Exception`. Quem captura precisa poder
distinguir.

**R-STD-20 — `catch` vazio é proibido.**
Se a falha é mesmo ignorável, o `catch` registra por que (`observability.md`,
`R-OBS-05`). Silêncio absoluto esconde defeito por meses.

**R-STD-21 — Mensagem de erro para humano não vaza detalhe interno.**
Stack trace, query SQL e caminho de arquivo vão para o log. Para o usuário vai
o que ele pode fazer a respeito.

---

## Referências

- Arquitetura e camadas: `core/architecture.md`
- Padrões e anti-patterns: `core/patterns.md`
- Validação de entrada: `engineering/validations.md`
- Logs e métricas: `quality/observability.md`
