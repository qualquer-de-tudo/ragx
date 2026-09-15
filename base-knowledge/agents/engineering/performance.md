# Performance — otimizações obrigatórias

> **Quando carregar:** ao escrever consulta, laço sobre coleção, endpoint de
> listagem, job em lote ou qualquer coisa que rode por item.

Regra que governa todas as outras: **meça antes, meça depois.** Otimização sem
número é palpite, e palpite costuma piorar a legibilidade sem melhorar o tempo.

---

## Banco de dados

**R-PER-01 — N+1 é defeito, não "lentidão".**
Laço que consulta por item precisa virar carga em lote (eager loading, `IN`,
join). É o achado mais comum e o de maior impacto.

**R-PER-02 — `SELECT *` só em busca por chave primária.**
Listagem traz as colunas que usa. Coluna `TEXT` grande carregada à toa é
tráfego, memória e cache desperdiçados.

**R-PER-03 — Toda coluna de `WHERE`, `JOIN` e `ORDER BY` frequente tem índice.**
E todo índice novo é justificado — índice também custa em escrita
(`ai/dba.md`).

**R-PER-04 — Listagem sempre pagina, com teto.**
Sem teto, um parâmetro derruba a aplicação (`R-VAL-14`). Para conjunto grande,
paginação por cursor em vez de `OFFSET`: `OFFSET 100000` varre 100 mil linhas
para descartar.

**R-PER-05 — Agregue no banco, não na aplicação.**
`COUNT`, `SUM`, `GROUP BY` no SQL. Trazer 50 mil linhas para somar em PHP é
tempo de rede e memória jogados fora.

**R-PER-06 — Escrita em massa é uma operação, não um laço.**
`insert` em lote, `upsert`, `UPDATE ... WHERE id IN`. Mil `INSERT` são mil
viagens de rede.

**R-PER-07 — Transação curta.**
Ela segura conexão e cria contenção. Nada de I/O externo dentro dela
(`R-ARC-17`).

**R-PER-08 — Consulta em tabela grande tem `EXPLAIN` lido antes do merge.**
"Grande" = a partir de centenas de milhares de linhas, ou o que o projeto
definir.

---

## Cache

**R-PER-09 — Só cacheie o que é caro E estável.**
Cache de coisa barata adiciona complexidade e uma nova classe de bug
(dado velho) sem ganho.

**R-PER-10 — Todo cache tem TTL e chave versionada.**
Chave inclui a versão do formato: `invoice:v2:{id}`. Mudou o formato, a chave
velha expira sozinha em vez de entregar dado incompatível.

**R-PER-11 — Invalidação é planejada, não lembrada.**
Se não dá para invalidar com confiança, TTL curto é mais honesto que
invalidação que às vezes falha.

**R-PER-12 — Nunca cacheie resposta específica de usuário em cache
compartilhado.**
É como um usuário vê o dado de outro — vazamento, não bug de performance.

**R-PER-13 — Cache não substitui índice.**
Cachear consulta lenta esconde o problema até o cache esvaziar, e aí tudo cai
junto.

---

## Aplicação

**R-PER-14 — Trabalho que o usuário não precisa esperar sai do request.**
E-mail, PDF, webhook, sincronização: fila.

**R-PER-15 — Chamada externa tem timeout, retry com backoff e limite.**
Cliente HTTP sem timeout trava o worker até o fim do mundo. Retry sem backoff
derruba o parceiro e depois você.

**R-PER-16 — Não carregue coleção inteira na memória.**
Processe por chunk/cursor. `->all()` sobre uma tabela é um incidente esperando.

**R-PER-17 — Trabalho constante fora do laço.**
Consulta, compilação de regex e leitura de config feitas por iteração.

**R-PER-18 — Compressão e paginação em toda resposta de API que cresce.**

---

## Frontend e ativos

**R-PER-19 — Imagem em formato e tamanho adequados, com dimensão declarada.**

**R-PER-20 — Carregue depois o que não aparece na primeira tela.**

---

## Como o agente age

1. **Mede primeiro.** Quantidade de queries, tempo, memória. Sem número, não
   há otimização — há reescrita especulativa.
2. **Corrige o que é defeito** (N+1, falta de índice, ausência de paginação,
   chamada sem timeout) dentro da tarefa.
3. **Não faz micro-otimização especulativa.** Trocar código claro por código
   obscuro sem medida é `A-PAT-12`.
4. **Registra o que encontrou fora do escopo** em `quality/tech-debt.md`, com
   o número medido — débito de performance sem número não é priorizável.
5. **Reporta o resultado honestamente**: "de 340 ms para 45 ms, 112 queries
   para 3". Se não melhorou, diz que não melhorou.

---

## Referências

- Banco, índices e modelagem: `ai/dba.md`
- Limites de entrada: `engineering/validations.md`
- Métricas e rastreamento: `quality/observability.md`
- Anti-patterns: `core/patterns.md` (`A-PAT-03`, `A-PAT-05`)
