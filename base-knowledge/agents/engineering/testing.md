# Testing — testes automatizados

> **Quando carregar:** em toda tarefa que produz ou altera código.

Um teste serve para uma coisa: **permitir mudar o código sem medo.** Teste que
não faz isso — que quebra a cada refatoração, que passa com o código errado, ou
que ninguém entende quando falha — é custo sem benefício.

---

## O que testar

**R-TST-01 — Toda correção de bug começa por um teste que falha.**
Sem isso não há prova de que o bug existia, nem garantia de que não volta.

**R-TST-02 — Regra de negócio tem teste unitário.**
Cálculo, política, invariante, máquina de estado. É o teste mais barato e o que
mais paga.

**R-TST-03 — Todo endpoint tem teste de integração.**
Caminho feliz, erro de validação, e negação de acesso. Os três.

**R-TST-04 — Autorização é testada explicitamente.**
"Usuário B não acessa recurso de A" é um teste, não uma suposição
(`R-VAL-09`).

**R-TST-05 — Borda antes de volume.**
Vazio, nulo, um elemento, limite exato, limite + 1, negativo, unicode,
duplicado. É onde os defeitos estão.

**R-TST-06 — Teste o contrato de integração externa, não o fornecedor.**
Dublê para o cliente HTTP; um teste de contrato garante que o formato esperado
continua valendo.

---

## O que NÃO testar

**R-TST-07 — Não teste o framework.**
Que o ORM salva, que o roteador roteia, que o validador valida. É teste do
fornecedor.

**R-TST-08 — Não teste getter e setter triviais.**
Cobertura inflada, valor zero.

**R-TST-09 — Não teste detalhe de implementação.**
Asserção sobre "chamou o método privado X" quebra em toda refatoração e não
prova comportamento. Teste o que entra e o que sai.

---

## Como escrever

**R-TST-10 — Arrange / Act / Assert, visivelmente separados.**
Uma linha em branco entre os blocos basta.

**R-TST-11 — O nome do teste descreve comportamento e condição.**
`test_recusa_saque_quando_saldo_insuficiente`, não `test_withdraw_2`.
Quando falha no CI às 3 da manhã, o nome precisa bastar.

**R-TST-12 — Uma asserção conceitual por teste.**
Várias linhas de `assert` sobre o mesmo fato tudo bem; dois fatos diferentes
são dois testes.

**R-TST-13 — Teste é determinístico.**
Sem `sleep`, sem depender de ordem de execução, sem `rand` não semeado. Data e
hora entram por relógio injetável.

**R-TST-14 — Teste é isolado.**
Banco transacional ou recriado, filas falsas, cache limpo. Rodar sozinho e
rodar na suíte dão o mesmo resultado.

**R-TST-15 — Dado de teste é explícito no que importa.**
Factory para o ruído, valor literal para o que o teste está provando. Quem lê
precisa ver o número que gera a asserção.

**R-TST-16 — Zero dado real em teste.**
Nada de CPF, e-mail ou cartão de gente de verdade em fixture — nem anonimizado
"o suficiente" (`ai/dpo.md`).

**R-TST-17 — Teste lento tem etiqueta.**
Marcado e separável, para que a suíte rápida continue rápida. Uma suíte que
demora 20 minutos deixa de ser rodada.

---

## Pirâmide

```
     ╱ E2E ╲          poucos — os 3 a 5 fluxos que dão dinheiro
    ╱───────╲
   ╱ integr. ╲        endpoints, repositórios, jobs
  ╱───────────╲
 ╱   unitário  ╲      a maior parte — rápido, sem I/O
╱───────────────╲
```

**R-TST-18 — Se o teste unitário precisa de banco, o desenho está errado.**
A regra não deveria conhecer persistência (`R-ARC-02`). Ou a dependência sobe
para interface, ou o teste é de integração — assumidamente.

---

## Cobertura

**R-TST-19 — Cobertura mínima de 80% em código novo; 100% em regra de negócio
e em segurança.**

**R-TST-20 — Cobertura é piso, não meta.**
100% de cobertura com asserção fraca prova apenas que o código roda sem
estourar. A pergunta certa é "que mudança errada este teste pegaria?".

**R-TST-21 — Cobertura não pode cair no PR.**
Se caiu, ou faltou teste, ou código morto entrou junto.

---

## O que o agente faz

1. Escreve o teste **no mesmo commit** da mudança. Nunca "depois".
2. Roda a suíte antes de declarar a tarefa concluída e **relata o resultado
   real** — inclusive falhas. Teste vermelho não vira "pronto com ressalva".
3. Não altera teste para fazê-lo passar sem entender por que falhou. Teste que
   ficou vermelho ou achou um bug, ou documentava um comportamento que mudou
   de propósito — e aí a mudança de comportamento é que precisa de aprovação.
4. Não apaga nem marca como ignorado um teste que atrapalha. Isso é `R-GRD`
   material: pede aprovação, com o motivo.

---

## Referências

- Validação de entrada: `engineering/validations.md`
- Segurança: `engineering/security.md`
- Revisão: `quality/code-review.md`
- Performance sob carga: `engineering/performance.md`
