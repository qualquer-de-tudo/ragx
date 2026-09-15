# RAGX Integration — o agente e o índice de conhecimento

> **Quando carregar:** no início de qualquer sessão em projeto que tenha RAGX.
> **Depende de:** `ai/agent-behavior.md` (o fluxo de 6 passos). Este arquivo
> diz **como** executar o passo 1 daquele fluxo quando existe um índice.

O passo 1 de `agent-behavior.md` manda ler o contexto antes de agir. Sem
índice, "ler o contexto" significa abrir arquivos e torcer para abrir os
certos. Com o RAGX, significa perguntar.

---

## Onde o RAGX ajuda e onde não

| Pergunta | Ferramenta | Confiança |
|---|---|---|
| Que tecnologias e serviços este projeto tem? | `get_dictionary` | alta |
| Onde está a implementação de X? | `search_hybrid` | alta se `matched_by` inclui `keyword` |
| Quem chama / o que depende de Y? | `search_graph`, `get_entity` | média — o grafo é derivado |
| Monte o contexto para esta tarefa | `build_context` | alta dentro do orçamento |
| Qual o conteúdo deste trecho? | `get_chunk` | alta |
| Que regra da casa se aplica aqui? | `search_hybrid` em `@base/...` | alta |
| Qual o valor de uma variável de ambiente? | **nenhuma** | o índice não tem segredo, por construção |
| O que mudou no último deploy? | **nenhuma** | não é um índice de histórico |

**R-RGX-01 — O índice responde sobre o código indexado. Nada além.**
Se a resposta não está lá, diga que não está. Preencher lacuna com suposição é
exatamente o erro que o índice existe para evitar.

---

## Ordem de consulta

**R-RGX-02 — Comece pelo dicionário, sempre.**
`get_dictionary` custa poucos milhares de tokens e evita o erro mais caro do
agente: inventar a arquitetura. Uma vez por sessão.

**R-RGX-03 — Localize com busca híbrida, aprofunde com `get_chunk`.**
`search_hybrid` devolve trechos curtos e ordenados. Só abra o que importa.

**R-RGX-04 — Use `build_context` quando for implementar.**
Ele respeita um orçamento de tokens, deduplica e devolve as fontes. Somar
resultados de busca à mão estoura o contexto e repete conteúdo.

**R-RGX-05 — Leia `matched_by` antes de confiar.**
`keyword` = o termo literal existe no código. `semantic` = parecença de
sentido, que pode ser coincidência. Resultado só semântico com score baixo
merece verificação antes de virar afirmação.

**R-RGX-06 — Atualize o índice no início da tarefa, não a cada pergunta.**
`refresh` aplica o que mudou no disco. Reindexar antes de cada busca é
desperdício; raciocinar sobre o código de ontem é pior.

---

## Conhecimento base (`@base/...`)

Resultados com caminho começando em `@base/` vêm de repositórios de regras
compartilhadas — como este aqui — e não do projeto.

**R-RGX-07 — `@base/` é referência; o código do projeto é a realidade.**
Quando os dois divergirem, o projeto ganha, e a divergência vira nota em
`quality/decision-log.md`.

**R-RGX-08 — Cite a regra pelo ID.**
"`R-VAL-09` — identificador de outra entidade precisa ser validado como
acessível" é verificável. "boa prática de segurança" não é.

---

## Onde isso entra no fluxo de 6 passos

**Passo 1 — Leitura de contexto**
`refresh` → `get_dictionary` → `search_hybrid` sobre o assunto da tarefa →
`get_entity` para descobrir dependências. Antes de abrir arquivo.

**Passo 2 — Planejamento (`.plan.md`)**
`R-APR-01` exige listar arquivos tocados e riscos. `search_graph` responde
"quem mais depende disto" — é o insumo de `R-RSK-03` que costuma faltar.

**Passo 3 — Aprovação humana**
O índice não participa. Aprovação é de gente.

**Passo 4 — Execução**
`search_hybrid` para achar o padrão já usado no projeto antes de inventar um
novo. Consistência com o módulo vale mais que consistência com esta base.

**Passo 5 — Revisão (`.review.md`)**
`search_hybrid` pelo padrão corrigido: se a falha existe num lugar, costuma
existir em outros (`R-BLU-04`).

**Passo 6 — Decision log**
Antes de registrar uma decisão, busque se ela já foi tomada. Decisão
contraditória registrada duas vezes é pior que nenhuma.

---

## Limites que não se contornam

**R-RGX-09 — Nenhuma ferramenta do RAGX lê o filesystem.**
`get_document("caminho")` consulta o índice por aquele caminho; não abre o
arquivo. `not_found` significa "não indexado" — e às vezes significa
"bloqueado por conter segredo". Nos dois casos, a resposta é a resposta.

**R-RGX-10 — Arquivo com credencial não está no índice e não estará.**
O gate de segurança o bloqueia antes do parser. Precisa do conteúdo de um
`.env`? Peça ao humano. Não existe ferramenta, flag ou fraseado que devolva
isso.

**R-RGX-11 — Resposta grande é recusada, não truncada.**
Se você recebeu conteúdo, ele está completo. Código `too_large` significa
reduzir `limit` ou `tokens` e paginar — nunca supor o que faltou.

**R-RGX-12 — Escrita no índice não é escrita no código.**
`reindex`, `sync` e `rebuild_graph` mudam o que o agente **sabe**. Nenhum deles
mexe em arquivo do projeto. O que mexe em código continua passando por
`ai/approval-flow.md`.

---

## Quando o índice está errado

Acontece: arquivo criado agora, `sync` pendente, grafo desatualizado.

1. `refresh` — resolve a maioria dos casos
2. `sync` — depois de mudança estrutural (muitos arquivos movidos, merge
   grande)
3. Ainda divergente → **diga ao humano**, não contorne em silêncio

**R-RGX-13 — Índice desatualizado que o agente não reporta é a pior falha
possível:** respostas confiantes sobre um código que não existe mais.

---

## Referências

- Fluxo geral: `ai/agent-behavior.md`
- Aprovação: `ai/approval-flow.md`
- Leitura de módulo: `ai/module-context-reader.md`
- Roteamento: `ai/triggers.md`
