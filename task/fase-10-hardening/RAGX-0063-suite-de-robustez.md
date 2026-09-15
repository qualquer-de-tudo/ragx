# RAGX-0063 — Suíte de robustez

| | |
|---|---|
| **Fase** | 10 — Hardening + Release |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0062` |
| **Bloqueia** | `RAGX-0064`, `RAGX-0065` |
| **Documentação** | [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Cobrir os casos que quebram em uso real e não aparecem em teste feliz.

## Entregáveis

- [ ] Teste para cada linha da lista de robustez do doc 13 (encoding, bordas de arquivo, caminhos, symlink, concorrência, falhas de recurso)
- [ ] Degradação verificada: embedder offline → keyword com aviso; banco corrompido → mensagem + sugestão de `ragx reset`
- [ ] Lock de projeto: duas instâncias simultâneas não corrompem o banco
- [ ] Casos de reidratação: arquivo movido, truncado, com linhas removidas, com CRLF trocado
- [ ] Hub com projeto cujo caminho registrado sumiu → marcado `missing`, não removido

## Fora de escopo

- Testes de carga distribuída

## Critérios de aceite

- [ ] Todos os casos da lista têm teste e passam nos dois SOs
- [ ] Nenhum caso resulta em traceback não tratado
- [ ] Toda mensagem de erro indica o que fazer em seguida

## Testes

- [ ] A própria suíte é o entregável

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
