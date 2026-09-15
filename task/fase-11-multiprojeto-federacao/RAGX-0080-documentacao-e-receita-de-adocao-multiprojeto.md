# RAGX-0080 — Documentação e receita de adoção multiprojeto

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0079` |
| **Bloqueia** | — |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

Tornar a adoção em um ambiente de microsserviços uma receita seguível, não uma descoberta.

## Entregáveis

- [ ] Guia de adoção: do primeiro `ragx init` em 1 repositório até `--scope all` em N
- [ ] Receita de CI que publica a fatia de federação como artefato para quem não clona o repositório
- [ ] Seção de troubleshooting: vínculo não resolvido, modelo divergente, hub desatualizado, projeto `missing`
- [ ] Revisão dos docs 16 e 17 contra o comportamento implementado
- [ ] Exemplos reais de saída de `ragx hub link`, `ragx hub status` e `ragx hub dictionary`

## Fora de escopo

- Tutorial em vídeo

## Critérios de aceite

- [ ] Alguém que nunca viu o RAGX registra 3 repositórios e obtém uma resposta cross-project seguindo só o guia
- [ ] Toda saída de exemplo corresponde à saída real
- [ ] Cada item do troubleshooting tem causa, diagnóstico e correção

## Testes

- [ ] Extração dos comandos do guia e conferência contra `ragx --help` recursivo

## Notas

Fecha a Fase 11 e o escopo completo do produto.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
