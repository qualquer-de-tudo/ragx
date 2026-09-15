# RAGX-0064 — Guard rails de performance

| | |
|---|---|
| **Fase** | 10 — Hardening + Release |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0063` |
| **Bloqueia** | `RAGX-0066` |
| **Documentação** | [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Impedir regressão silenciosa de desempenho.

## Entregáveis

- [ ] Gerador de repositório sintético de 5.000 arquivos
- [ ] Medição dos 5 limites do doc 13 (index frio, index sem mudanças, search, context, mcp cold start)
- [ ] Falha de build em regressão acima de 30%
- [ ] Histórico de métricas publicado como artefato do CI

## Fora de escopo

- Otimização — esta tarefa mede; otimizar é ticket próprio a partir do que ela apontar

## Critérios de aceite

- [ ] Os 5 limites são medidos e estão dentro do alvo na máquina de referência
- [ ] Regressão acima de 30% falha o build
- [ ] Medição é estável o bastante para não gerar falso alarme

## Testes

- [ ] Job de performance no CI

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
