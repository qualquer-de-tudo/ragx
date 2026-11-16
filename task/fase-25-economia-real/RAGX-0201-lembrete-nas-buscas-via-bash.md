# RAGX-0201 — Lembrete também nas buscas via Bash

| | |
|---|---|
| **Fase** | 25 — Economia real |
| **Prioridade** | P1 |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) |
| **Status** | `review` |

## Objetivo

O lembrete de busca (`PreToolUse`) só dispara em `Grep|Glob`. No Juriflux o agente fez 12.962 buscas via Bash
(`grep`, `rg`, `find`, `ls`, `Select-String`, `Get-ChildItem`) e 1.599 pelo Grep: o lembrete não vê a maior parte
das buscas. Ele passa a disparar também em `Bash` quando o comando é de busca.

## Entregáveis

- [x] Matcher do hook `Grep|Glob|Bash`; no Bash, o lembrete só sai quando o comando é de busca (detecção pelo
      primeiro programa de cada trecho do comando); comando que não é busca sai em silêncio, sem custo
- [x] Continua uma vez por sessão (e por subagente); nunca bloqueia, nunca falha
- [x] `ragx claude heal` atualiza o matcher dos perfis que já têm o lembrete
- [x] Latência do hook no Bash dentro do teto do lembrete (o Bash dispara muito mais vezes que o Grep)

## Fora de escopo

- Bloquear ou reescrever o comando do agente
- Lembrete em `Read`

## Critérios de aceite

- [x] Testes: busca via Bash recebe o lembrete; `npm test`, `git status` e afins não; segunda busca na mesma sessão não
- [x] Perfil instalado numa versão antiga ganha o matcher novo pelo `heal`
