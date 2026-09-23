# RAGX — Painel Desktop

Painel Electron local para o RAGX: mostra os projetos registrados no hub
(`~/.ragx/hub/registry.json`), contagem de documentos/chunks/embeddings de
cada um, telemetria de chamadas MCP das últimas 24h, e resultados sob demanda
de `ragx trial` (economia estimada) e `ragx security scan` (achados de
segurança). Roda 100% local, sem login e sem enviar dados para fora da
máquina — lê arquivos e bancos SQLite locais e invoca o CLI `ragx` já
instalado no sistema.

## Comandos

```bash
npm run dev:electron   # modo desenvolvimento (Vite + Electron com hot reload)
npm run build           # build do renderer (Vite) + checagem de tipos
npm run package          # gera o instalador Windows (.exe) em release/
npm test                  # suíte de testes (vitest)
npm run lint               # eslint
```

## Estrutura

- `src/` — UI React (renderer process).
- `electron/` — main process: leitura do registry/hub, stats via `sql.js`,
  telemetria (`electron/data/telemetry.ts`) e execução do CLI `ragx`
  (`electron/data/run-ragx-command.ts`).
