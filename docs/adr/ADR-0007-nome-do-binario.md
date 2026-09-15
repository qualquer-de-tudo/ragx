# ADR-0007 — Binário `ragx`, pacote `ragx`

**Status:** aceito · 2026-09-15 · **revisado em 2026-09-15 (Fase 11)**

> **Revisão.** A decisão original elegeu `rag` como comando primário e `ragx`
> como alias. Invertido: **`ragx` é o primário**, `rag` continua funcionando
> como alias histórico. O motivo está em "Revisão" ao final.

## Contexto

O plano de MVP especifica todos os comandos com o prefixo `rag` — `rag init`,
`rag index .`, `rag search "..."`. O diretório do projeto chama-se `ragx`.
`rag` é um nome curto e genérico, com risco real de colisão com outro executável
no PATH do usuário e provavelmente indisponível no PyPI.

## Decisão

- **Nome de distribuição e pacote Python:** `ragx` (`import ragx`, `pip install ragx`).
- **Console script primário:** `ragx`.
- **Alias:** `rag`, apontando para o mesmo entrypoint.

```toml
[project.scripts]
ragx = "ragx.cli.main:main"
rag  = "ragx.cli.main:main"
```

- `ragx doctor` detecta colisão: se `rag` no PATH resolver para outro executável,
  emite aviso e instrui a usar `ragx`.
- Toda documentação usa `ragx`; o alias é mencionado uma vez, aqui e no README.

## Consequências

Positivas:
- Um nome só, igual ao do pacote e ao do diretório do projeto.
- Nome de pacote inequívoco, sem disputa no PyPI.
- Usuário com conflito no PATH tem saída imediata.

Negativas:
- Dois nomes para a mesma coisa exige uma linha de explicação no README.
- Documentação precisa ser consistente em usar `ragx`; mistura confunde.

## Alternativas rejeitadas

- **Só `ragx`** — divergiria de toda a especificação já escrita.
- **Só `rag`** — risco de colisão e de indisponibilidade do nome no PyPI.
- **`ragx` com sugestão de alias manual** — empurra configuração de shell para o
  usuário, e não funciona igual em PowerShell, bash e zsh.

---

## Revisão — 2026-09-15 (Fase 11)

`rag` era o comando primário porque era o que o plano de MVP escrevia. Três
coisas mudaram isso:

1. **Colisão real.** `rag` é curto e genérico demais; o `doctor` previa o
   conflito, mas prevenir é melhor que diagnosticar.
2. **Um nome só.** Pacote `ragx`, diretório `ragx`, servidor MCP `ragx`,
   configuração `ragx.toml` — e o comando era `rag`. A inconsistência aparecia
   em toda página de documentação.
3. **Pedido explícito do usuário**, que é a razão imediata da revisão.

`rag` **não foi removido**: script, alias de shell e configuração de MCP já
existentes continuam funcionando. Remover quebraria instalações por ganho
nenhum.

A migração foi textual e verificável: 417 ocorrências em 68 arquivos de
documentação e board, 85 em 34 módulos de código (mensagens ao usuário e
docstrings). Prosa em português onde "rag" é substantivo — "o rag exportado" —
ficou intocada.
