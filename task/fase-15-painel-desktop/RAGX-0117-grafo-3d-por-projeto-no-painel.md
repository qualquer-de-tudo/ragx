# RAGX-0117: Grafo 3D por projeto no painel

| | |
|---|---|
| **Fase** | 15: Painel desktop |
| **Prioridade** | P2: média (adiada por decisão da pessoa) |
| **Estimativa** | MVP 3 a 4d · completo 7 a 10d |
| **Depende de** | nenhuma |
| **Documentação** | [docs/06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` (adiada; precisa de spec antes de implementar) |

## Objetivo

Ver, na página de cada projeto, o grafo de conhecimento em 3D (entidades e arestas), navegável, como referência inspirada no graphify.

## Levantamento (2026-09-23)

- **Os dados já existem.** As tabelas `entities` e `relations` de cada `knowledge.db` são populadas por `ragx graph rebuild`. No próprio repositório do RAGX: 1.795 entidades (995 `function`, 387 `file`, 212 `method`, 155 `class`, 34 `table`, 7 `technology`, 5 `endpoint`) e 10.395 relações (5.265 `calls`, 2.997 `documented_by`, 1.422 `contains`, 625 `mentions`, 79 `imports`, 7 `uses`).
- `ragx graph show <entidade> --json` já devolve `{nodes, edges}`, mas só da vizinhança de uma entidade (profundidade 1 a 3). **Não existe exportação do grafo inteiro.**
- O painel já lê o `knowledge.db` de cada projeto (sql.js) e já tem o padrão de pedido por id de projeto validado no processo principal: uma tela de grafo entra no mesmo molde, com um método somente leitura.
- **O graphify não é 3D.** Ele usa `vis-network` (2D, física de mola), limita a 5.000 nós e, acima disso, mostra uma visão agregada por comunidade. Ainda assim é um bom modelo de interação.
- 3D de verdade é viável: `3d-force-graph` (three.js) roda no Chromium do Electron sem dependência nativa.
- A dificuldade real é escala e poluição visual: com 1.700+ nós (e projetos maiores), o grafo fica ilegível sem filtro, busca com foco, limite de nós ou agrupamento.

## Entregáveis (esboço, a refinar no brainstorming)

- [ ] `ragx graph export --json` (grafo inteiro com filtros por tipo de entidade e de relação), ou leitura direta no painel
- [ ] Método de leitura no IPC, por id de projeto, sem caminho vindo do renderer
- [ ] Tela "Grafo" no detalhe do projeto: navegação 3D, clique em nó mostra a vizinhança e a origem (arquivo e trecho)
- [ ] Filtros por tipo de entidade e de relação, busca com foco, limite de nós
- [ ] Agrupamento por comunidade para grafos grandes (versão completa)

## Fora de escopo

- Editar o grafo pela interface
- Grafo entre projetos (federação)

## Critérios de aceite

- [ ] O grafo do próprio RAGX (1.795 nós) abre e navega sem travar
- [ ] Nenhum trecho de código ou segredo vai para o renderer além do que o índice já contém
- [ ] Visual no mesmo padrão escuro do painel; nenhum travessão em texto visível

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] `npm test`, `npm run lint`, `tsc` e `uv run pytest -m "not slow"` limpos
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Verificado no app Electron de verdade
