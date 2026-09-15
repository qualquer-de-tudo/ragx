# Patterns — padrões obrigatórios e anti-patterns

> **Quando carregar:** ao escrever código novo e em toda revisão.
> **Como usar:** `R-PAT-*` são obrigações. `A-PAT-*` são anti-patterns — se o
> agente estiver prestes a produzir um, ele para e propõe a alternativa.

---

## Padrões obrigatórios

**R-PAT-01 — Injeção de dependência por construtor.**
Nada de `new` de colaborador dentro de método, nada de service locator, nada de
singleton global. O que a classe precisa aparece na assinatura — é o que torna
o teste possível sem mágica.

**R-PAT-02 — Um motivo para mudar, por classe.**
Se a descrição da classe precisa de "e", são duas classes.

**R-PAT-03 — Depender de abstração na fronteira.**
Domínio depende da interface `PaymentGateway`, não de `StripeClient`. Dentro
de um módulo, depender da classe concreta é aceitável — interface para tudo é
cerimônia sem ganho.

**R-PAT-04 — Retorno cedo em vez de aninhamento.**
Trate o caso excepcional e saia. Três níveis de `if` aninhado quase sempre são
três guard clauses mal escritas.

**R-PAT-05 — Imutabilidade por padrão em DTO e Value Object.**
Objeto que muda de valor no meio do fluxo é a origem de bug que ninguém
reproduz.

**R-PAT-06 — Estado inválido deve ser irrepresentável.**
Prefira enum a string livre; prefira um construtor que valida a um setter que
aceita qualquer coisa. Validar na borda é bom; impedir no tipo é melhor.

**R-PAT-07 — Erro esperado tem tipo próprio.**
"Saldo insuficiente" é um caso de negócio, não uma `Exception` genérica. Quem
chama precisa distinguir isso de "banco caiu".

**R-PAT-08 — Idempotência em tudo que a fila pode repetir.**
Ver `core/architecture.md`, `R-ARC-18`.

**R-PAT-09 — Composição antes de herança.**
Herança só quando há substituibilidade real (Liskov). "Herdei para reaproveitar
três métodos" é composição disfarçada.

**R-PAT-10 — Factory quando a construção tem regra.**
Se montar o objeto exige mais que passar os campos, isso é conhecimento de
domínio e merece um lugar nomeado.

---

## Anti-patterns — o agente não produz

**A-PAT-01 — God Object.**
Classe que valida, calcula, persiste, notifica e formata.
→ Separe por camada (`core/architecture.md`).

**A-PAT-02 — Lógica de negócio no Controller.**
`if` de regra, cálculo, decisão de fluxo.
→ Mova para Action/Service.

**A-PAT-03 — Query dentro de Controller ou de View.**
→ Repository. Em view, é N+1 garantido (`engineering/performance.md`).

**A-PAT-04 — Array associativo cruzando camadas.**
`['user' => ['name' => ...]]` passado adiante não tem contrato: o erro só
aparece onde a chave falta.
→ DTO tipado.

**A-PAT-05 — N+1.**
Laço que consulta o banco a cada iteração.
→ Eager loading / carga em lote (`R-PER-01`).

**A-PAT-06 — Número e string mágicos.**
`if ($status === 3)`.
→ Enum ou constante nomeada.

**A-PAT-07 — `catch (Exception) {}` vazio.**
→ Trate, ou registre e relance (`R-STD-20`).

**A-PAT-08 — Segredo no código.**
Chave, token ou senha literal — mesmo "só para testar", mesmo em branch que
"não vai subir". O histórico do Git é permanente.
→ Variável de ambiente, imediatamente.

**A-PAT-09 — Concatenação em query.**
`"WHERE id = " . $id` é SQL injection.
→ Parâmetro vinculado, sem exceção (`R-SEC-01`).

**A-PAT-10 — Copiar e colar bloco de regra.**
A terceira cópia é onde o bug divergente nasce.
→ Extraia. (Duas cópias ainda podem ser coincidência; três, não.)

**A-PAT-11 — Flag booleana de parâmetro que troca o comportamento.**
`process($data, true)` — ilegível no ponto de chamada.
→ Dois métodos com nomes honestos.

**A-PAT-12 — Abstração especulativa.**
Interface com uma implementação, camada "para quando precisar", generalização
de um caso único.
→ Resolva o problema de hoje. O de amanhã tem requisitos que você ainda não
conhece.

**A-PAT-13 — Regra de negócio dentro de migration ou seeder.**
→ Migration move schema; regra vive no domínio.

**A-PAT-14 — Estado global mutável.**
Variável estática, singleton com setter, config alterada em runtime.
→ Passe explicitamente.

**A-PAT-15 — Refatoração oportunista junto da feature.**
Mistura o que é comportamento novo com o que é forma, e torna a revisão e o
rollback impossíveis.
→ Commit separado (`engineering/refactoring.md`).

---

## Como o agente aplica

1. Antes de escrever, verifica se o padrão do módulo já contradiz esta página.
   Se contradiz de forma consistente, **o módulo ganha** — e a divergência vira
   nota em `quality/decision-log.md`.
2. Ao detectar um anti-pattern no código existente que **não faz parte da
   tarefa**, não conserta de passagem: registra em `quality/tech-debt.md`.
3. Ao estar prestes a produzir um anti-pattern por pedido explícito do humano,
   diz qual é, qual o custo, propõe a alternativa — e, se o humano confirmar,
   faz o que foi pedido e registra a decisão.

---

## Referências

- Camadas e fronteiras: `core/architecture.md`
- Convenções de código: `core/standards.md`
- Checklist de revisão: `quality/code-review.md`
- Registro de débito: `quality/tech-debt.md`
