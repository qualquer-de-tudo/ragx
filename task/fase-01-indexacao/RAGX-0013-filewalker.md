# RAGX-0013 — FileWalker

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0012` |
| **Bloqueia** | `RAGX-0021` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

Caminhar o repositório com segurança, produzindo candidatos em streaming.

## Entregáveis

- [ ] `indexing/walker.py` emitindo `FileCandidate(rel_path, size, mtime_ns, raw_bytes)`
- [ ] Recusa de symlink que aponta para fora da raiz; detecção de ciclo por inode
- [ ] Limite `index.max_file_bytes` → `skipped:too_large`
- [ ] Detecção de binário pelos primeiros 8 KiB (`\x00`) → `skipped:binary`
- [ ] Cascata de decodificação utf-8 → utf-8-sig → latin-1 → `skipped:undecodable`
- [ ] Integração com o IgnoreEngine e classificação de motivo de skip

## Fora de escopo

- Parsing

## Critérios de aceite

- [ ] Symlink para fora da raiz é recusado e registrado
- [ ] Symlink circular não trava o walker
- [ ] Repositório de 5.000 arquivos é percorrido sem carregar tudo em memória
- [ ] Caminho com acento, espaço e emoji funciona no Windows e no Linux
- [ ] Caminho longo (> 260 chars) no Windows é tratado

## Testes

- [ ] Integração com árvore sintética contendo todos os casos de borda do doc 13

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
