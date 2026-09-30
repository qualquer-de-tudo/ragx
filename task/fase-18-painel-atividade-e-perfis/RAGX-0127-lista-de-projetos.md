# RAGX-0127: Lista de projetos — resumo, números no card, ordenar/filtrar, grade/lista

| | |
|---|---|
| **Fase** | 18: Painel — atividade ao vivo, lista de projetos e perfis do Claude |
| **Prioridade** | P2 |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Status** | `done` |

## Objetivo

A lista de projetos mostra nome, estado e branch. Com vários projetos, falta
ver de relance quais estão sendo usados, quanto economizam e quais pedem atenção.

## Entregáveis

- [x] Faixa de resumo no topo: projetos, chamadas MCP nas últimas 24 h, tokens
      economizados em 14 dias, quantos precisam de atenção
- [x] Card com números: economia (%), chamadas em 24 h, documentos, última indexação
- [x] Ordenar por uso recente, nome ou estado; filtrar por estado
- [x] Alternar entre grade de cards e lista compacta (tabela), lembrado como a aba do detalhe

## Fora de escopo

- Novos dados do backend: tudo sai do snapshot que o painel já tem
- Agrupar por pasta ou cliente

## Critérios de aceite

- [x] Os números do card batem com os do detalhe do projeto
- [x] A lista compacta cabe em 960 px sem rolagem horizontal
- [x] Ordenação e filtro combinam com a busca que já existe

## Testes

vitest da página (resumo, ordenação, filtro, alternância) e do card.

## Definition of Done

- [x] Critérios verificados
- [x] CHANGELOG na mesma alteração
