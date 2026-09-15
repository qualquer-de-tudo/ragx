# RAGX-0055 — Formato .rag: manifest e checksums

| | |
|---|---|
| **Fase** | 8 — Export / Import (.rag) |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0045` |
| **Bloqueia** | `RAGX-0056` |
| **Documentação** | [11-export-import.md](../../docs/11-export-import.md) |
| **Status** | `todo` |

## Objetivo

Definir o contrato do pacote portátil antes de escrever exporter e importer.

## Entregáveis

- [ ] `portability/manifest.py` com o modelo do doc 11 e JSON Schema publicado
- [ ] Layout ZIP fixo, com `manifest.json` legível sem descompactar tudo
- [ ] `CHECKSUMS.sha256` cobrindo todos os arquivos do pacote
- [ ] `source.git_remote_hash` — hash do remote, nunca a URL (pode conter token)
- [ ] `ragx inspect <arquivo.rag> [--json]`
- [ ] Layout inclui `knowledge/federation/`; embeddings em int8 por padrão (`--full-vectors` é opt-in)

## Fora de escopo

- Exportar/importar de fato (RAGX-0056, RAGX-0057)

## Critérios de aceite

- [ ] `ragx inspect` lê o manifest sem descompactar o pacote inteiro
- [ ] Manifest valida contra o schema
- [ ] Nenhuma URL de remote em claro no pacote

## Testes

- [ ] Round-trip de manifest
- [ ] Teste de que a URL do remote não aparece

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
