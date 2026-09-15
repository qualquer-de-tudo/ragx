# RAGX-0040 — Compressão extrativa

| | |
|---|---|
| **Fase** | 4 — Context Engine |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0039` |
| **Bloqueia** | `RAGX-0041` |
| **Documentação** | [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

Caber no orçamento sem inventar conteúdo e sem perder a fonte.

## Entregáveis

- [ ] `context/compress.py` com as 4 estratégias do doc 07, aplicadas em ordem
- [ ] Poda de ruído (imports irrelevantes, licença de cabeçalho, comentário gerado)
- [ ] Colapso de corpo em código de baixa prioridade (`# ... (N linhas omitidas)`)
- [ ] Seleção de sentenças em documentação, sempre preservando a primeira da seção
- [ ] Truncamento marcado com `…(truncado)` como último recurso
- [ ] Flag `compressed` no fragmento

## Fora de escopo

- Resumo gerado por LLM — explicitamente rejeitado no MVP

## Critérios de aceite

- [ ] Fonte e intervalo de linhas preservados em 100% dos fragmentos comprimidos
- [ ] Compressão é determinística (mesma entrada, mesma saída)
- [ ] Assinatura de função nunca é removida
- [ ] Redução média >= 40% em chunks de código de baixa prioridade

## Testes

- [ ] Snapshot de compressão por estratégia
- [ ] Teste de preservação de fonte

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
