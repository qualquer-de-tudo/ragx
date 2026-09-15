# RAGX-0073 — Fatia de federação versionada

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0072` |
| **Bloqueia** | `RAGX-0074` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [16-orcamento-de-tamanho.md](../../docs/16-orcamento-de-tamanho.md) |
| **Status** | `todo` |

## Objetivo

Publicar a superfície pública como artefato versionado, autossuficiente e minúsculo — é o que permite a outro projeto usar o contrato sem clonar este repositório.

## Entregáveis

- [ ] `federation/slice.py` gerando `knowledge/federation/`: `service.json`, `provides.json`, `consumes.json`, `contracts/`, `glossary.json`
- [ ] Contratos embutidos **por valor** (OpenAPI/AsyncAPI/protobuf/JSON Schema quando existirem no repo)
- [ ] Re-scan de segurança antes de gravar; item que casa com regra de segredo é descartado com `security_event`
- [ ] Serialização estável (`sort_keys`, LF) — `git diff` vazio quando nada muda
- [ ] `ragx federation build [--manual FILE]` e `ragx federation show [--direction]`
- [ ] `ragx federation export <arquivo.fed.json>` — fatia avulsa em arquivo único
- [ ] `visibility = "private"` impede a geração da fatia

## Fora de escopo

- Consumo pelo hub (RAGX-0074)

## Critérios de aceite

- [ ] `knowledge/federation/` de um projeto real fica abaixo de 1 MB
- [ ] A fatia é autossuficiente: outro projeto a usa sem acesso a este repositório
- [ ] Nenhum caminho absoluto e nenhum segredo na fatia
- [ ] Projeto `private` não gera fatia
- [ ] Regeneração sem mudanças produz diff vazio

## Testes

- [ ] Varredura da fatia contra `SECRETS_UNDER_TEST`
- [ ] Teste de autossuficiência em diretório isolado

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
