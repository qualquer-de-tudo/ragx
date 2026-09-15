# RAGX-0008 — SecurityGate: fachada e invariante arquitetural

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0004`, `RAGX-0007` |
| **Bloqueia** | `RAGX-0009`, `RAGX-0021` |
| **Documentação** | [02-seguranca.md](../../docs/02-seguranca.md) · [adr/ADR-0008-security-gate-antes-do-parser.md](../../docs/adr/ADR-0008-security-gate-antes-do-parser.md) |
| **Status** | `todo` |

## Objetivo

Unificar IgnoreEngine, Scanner e Redactor numa única porta de entrada, e garantir por teste que ninguém a contorna.

## Entregáveis

- [ ] `security/gate.py` com `Verdict` (ALLOW / ALLOW_REDACTED / SKIP / BLOCK) e `GateDecision`
- [ ] API única: `gate.admit(path, raw) -> GateDecision`; `content` é `None` em SKIP/BLOCK
- [ ] Política `strict` / `balanced` conforme o doc 02
- [ ] Teste arquitetural: só `ragx.indexing.walker` e `ragx.sync.incremental` leem o filesystem do projeto
- [ ] Teste arquitetural (AST): nenhum caminho em `walker.py` entrega bytes sem passar por `admit()`

## Fora de escopo

- Uso do gate pelo pipeline real (RAGX-0021)

## Critérios de aceite

- [ ] Toda decisão carrega `rule_id` e lista de achados
- [ ] Política `strict` promove qualquer achado critical/high a `BLOCK` no arquivo inteiro
- [ ] Testes arquiteturais falham se alguém adicionar `open()` fora dos dois módulos permitidos

## Testes

- [ ] Arquiteturais (import graph + AST)
- [ ] Matriz política × severidade × veredito

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
