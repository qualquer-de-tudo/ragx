# RAGX-0203 — Busca enxuta por padrão e mapa de arquivo no perfil slim

| | |
|---|---|
| **Fase** | 25 — Economia real |
| **Prioridade** | P1 |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [09-mcp.md](../../docs/09-mcp.md) · [05-busca.md](../../docs/05-busca.md) |
| **Status** | `review` |

## Objetivo

No Juriflux, o `search_hybrid` devolveu ~2.200 tokens por chamada; um grep devolve ~400. Para "onde está X" o
agente faz bem em preferir o grep. A busca do RAGX passa a custar no máximo o que um grep custa, e o agente ganha
um mapa de arquivo (símbolos com linhas) para ler só o trecho de que precisa.

## Entregáveis

- [x] `search_hybrid` e `search_knowledge` no perfil slim: 5 resultados por padrão, cada um com caminho, linhas,
      símbolo e um trecho de uma linha; resposta de busca típica <= 600 tokens (medido no fio)
- [x] `get_document` (o mapa: chunks com símbolo e linhas, sem conteúdo) entra no perfil slim, com descrição curta;
      custo fixo do slim continua <= 600 tokens
- [x] Benchmarks: ponto novo para "tokens por busca", com método e data

## Fora de escopo

- Mudar o `build_context`
- Mudar o ranking

## Critérios de aceite

- [x] Teste no fio: busca típica <= 600 tokens; `get_document` não devolve conteúdo de chunk
- [x] Custo fixo do slim <= 600 tokens (`test_mcp_perfis.py`)
