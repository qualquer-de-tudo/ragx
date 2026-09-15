# RAGX-0056 — Exporter com re-scan e verificação de integridade

| | |
|---|---|
| **Fase** | 8 — Export / Import (.rag) |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0055` |
| **Bloqueia** | `RAGX-0057` |
| **Documentação** | [11-export-import.md](../../docs/11-export-import.md) |
| **Status** | `todo` |

## Objetivo

Empacotar conhecimento com atestação de segurança, sem caminho de escape.

## Entregáveis

- [ ] `portability/exporter.py` com o pipeline scan → integridade → manifest → pacote
- [ ] Re-scan COMPLETO do conteúdo a ser empacotado (não confia no scan da indexação)
- [ ] Verificação de integridade: IDs conferem, sem chunk órfão, sem embedding sem chunk
- [ ] `--include-embeddings` (int8 por padrão; `--full-vectors` para float32) e `--include-agents`
- [ ] `ragx federation export <arquivo.fed.json>` — fatia pública avulsa, poucos KB
- [ ] Ao contrário de `knowledge/`, o pacote INCLUI o conteúdo dos chunks: precisa ser autossuficiente
- [ ] Bloqueio da lista do doc 11: caminho absoluto, conteúdo bloqueado, `security_events`, `.db`, logs
- [ ] Falha com exit 1 em qualquer achado critical/high — sem flag `--force`

## Fora de escopo

- Assinatura criptográfica do pacote — pós-MVP

## Critérios de aceite

- [ ] Export sobre a fixture de segredos falha com exit 1 e nomeia o achado
- [ ] Pacote descompactado e varrido por `grep` não contém nenhum segredo da fixture
- [ ] Nenhum caminho absoluto em nenhum arquivo do pacote
- [ ] Superfície `export` sem `xfail`

## Testes

- [ ] Varredura do pacote descompactado contra `SECRETS_UNDER_TEST`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
