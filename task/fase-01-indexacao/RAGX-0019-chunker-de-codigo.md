# RAGX-0019 — Chunker de código

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0016`, `RAGX-0017` |
| **Bloqueia** | `RAGX-0021` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

Transformar estrutura sintática em chunks autocontidos e citáveis.

## Entregáveis

- [ ] `indexing/chunkers/code_chunker.py` com as regras do doc 04
- [ ] Chunk de classe = cabeçalho (assinatura, docstring, atributos, lista de métodos), sem repetir corpos
- [ ] Chunk de preâmbulo do arquivo com imports e constantes de módulo
- [ ] Divisão de unidade acima de `max_tokens` por blocos lógicos, com sufixo `#part-N`
- [ ] Fusão de unidade abaixo de `min_tokens` com a vizinha de mesmo pai
- [ ] `parent_id` ligando método → classe → arquivo
- [ ] Prefixo de contexto aplicado só na geração de embedding, nunca em `chunks.content`

## Fora de escopo

- Geração de embedding

## Critérios de aceite

- [ ] Nenhum chunk corta uma função ao meio (exceto divisão explícita com `#part-N`)
- [ ] Getters triviais são fundidos em vez de gerar dezenas de chunks de 3 linhas
- [ ] `token_count` gravado e coerente com o TokenCounter
- [ ] Fatiamento determinístico: mesma entrada, mesma saída, mesmos IDs

## Testes

- [ ] Snapshot de chunking sobre fixtures por linguagem

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
