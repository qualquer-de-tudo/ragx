# RAGX-0161 — Subagente `ragx-explorer` instalável

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-05, 7.2 #10) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T7) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `done` |

## Objetivo

Explorar código num repositório grande enche o contexto do agente principal com leituras que ele não vai reusar. Um subagente explorador isola essa exploração e devolve só o resumo: é o mesmo desenho do SWE-grep do Windsurf (7.2 #10) e uma forma de pôr o RAGX **no caminho** do modelo, em vez de depender de ele lembrar (M-05: 3 de 38 sessões chamaram). Hoje o RAGX não instala nenhum subagente. Esta tarefa gera e instala o `ragx-explorer.md`, opt-in, em cada perfil do Claude Code.

## Entregáveis

- [x] **Conferir o formato antes:** na versão instalada do Claude Code (`claude --version`), confirmar o formato de subagente de usuário (arquivo `.md` com frontmatter `name`, `description`, `tools`, opcional `model`) e onde ele mora para o perfil padrão e para os de `CLAUDE_CONFIG_DIR`. Registrar em Andamento.
- [x] `src/ragx/clients/claude_agent.py` (novo): o texto do agente como constante Python (como `agents/profile.py` faz com `_INSTRUCTIONS`), com a linha `<!-- ragx:managed v1 -->` logo após o frontmatter. `tools`: `mcp__ragx__build_context`, `mcp__ragx__search_hybrid`, `mcp__ragx__get_chunk`, `mcp__ragx__get_entity`, `Read`, `Grep`, `Glob` (só leitura; sem `Edit`, `Write` nem `Bash`). Sem `model` (herda; a pessoa pode fixar um mais barato, documentado).
- [x] O corpo do agente: usar o RAGX primeiro (`build_context`, depois `get_chunk`/`get_entity`), `Read`/`Grep` só nos arquivos apontados, e **responder curto**: caminhos com linhas e 3 a 6 frases, sem colar trechos longos (é isso que poupa o contexto do principal).
- [x] `install_agent`, `remove_agent`, `has_agent` no mesmo módulo, usando `_backup` e `_escrever` de `clients/registry.py` (443-474) e o diretório `claude_settings(client).parent / "agents"` (registry.py:256-260). Arquivo existente **sem** o marcador (é da pessoa) não é sobrescrito: `Outcome.FAILED` com a explicação. Arquivo nosso de versão antiga é atualizado. `remove` só apaga arquivo com o marcador.
- [x] CLI: `ragx claude agent install|remove|status [--profile X] [--dry-run] [--json]` e `ragx claude on --agent/--no-agent` (**padrão desligado**: um subagente novo aparece na lista da pessoa). `ragx claude status --json` ganha `agent` por perfil (`_estado`, claude_cmd.py:49-66).
- [x] `docs/14-cli.md` (linhas 343-350) e `docs/GUIA-DE-USO.md` (linhas 176-177): o que o subagente faz, como instalar e como fixar o modelo. CHANGELOG.

## Fora de escopo

- Escolher o modelo do subagente por conta própria (fica herdado; decisão da pessoa).
- Instalar no `.claude/agents/` do repositório do usuário (só no nível do perfil, para não sujar o Git de ninguém).
- Subagente para outros clientes (Cursor, Codex, Gemini). Ajustar quando o Claude Code delega (a `description` é o único gatilho).
- Hooks (0160) e o texto do hint (0164).

## Critérios de aceite

- [x] `ragx claude agent install` num perfil de teste cria `agents/ragx-explorer.md`; o frontmatter é YAML válido e **toda** ferramenta `mcp__ragx__*` listada existe nos dois perfis do servidor (`full` e `slim`, da 0157).
- [x] Rodar de novo não muda nada; `remove` apaga só o arquivo com o marcador; arquivo da pessoa com o mesmo nome fica intacto.
- [x] A `description` custa ≤ **60 tokens** (ela entra no contexto do agente principal em toda sessão).

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens fixos no contexto principal (`name` + `description`) | 0 (não existe) | **48** (`description` 44; tiktoken cl100k; teto 60) |
| Tamanho do arquivo instalado, tokens (carregado só quando o subagente roda) | n/a | 356 |

O efeito em tokens do contexto principal só é mensurável pelo A/B da 0162; esta tarefa não declara número de economia.

## Testes

- [x] `tests/unit/test_claude_agent.py` (novo, com um `casa` como o de `test_claude_profiles_hint.py`, HOME redirecionado): instalar, idempotência, `--dry-run` sem escrita, arquivo alheio preservado, versão antiga atualizada, `remove`, vários perfis, `ragx claude status --json` com `agent`.
- [x] Mesmo arquivo: parse do frontmatter e conferência das ferramentas contra `build_server(cfg, profile=...).list_tools()` nos dois perfis (**falha** se alguém renomear uma ferramenta e esquecer o agente).
- [x] Teste do limite de 60 tokens da `description`.
- [x] Nada em `src/ragx/mcp` muda (invariante "MCP é casca fina" intacto); `tests/security` verde.

## Notas

- **O loop nunca instala no HOME real**: a pessoa decide rodar `ragx claude agent install`. Testes só com a fixture `casa`.
- Confirmado: `clients/registry.py:256-260` dá o diretório do perfil; `_backup`/`_escrever` já preservam o modo do arquivo e usam arquivo temporário (testes em `test_mcp_install.py:386-426`).
- Subagentes usam o mesmo servidor MCP do agente principal. Isso conversa com o dedupe de sessão (0159): o que o explorador recebeu não está no contexto do principal. Registrar a limitação em `docs/07-context-engine.md` se a 0159 estiver pronta.
- Se o Claude Code mudar o formato de subagente, o marcador `v1` serve para atualizar; o teste de frontmatter acusa a quebra.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0161)` na branch `feat/v2`

## Andamento

- 2026-10-01 — **Formato conferido na documentação** (code.claude.com/docs/en/sub-agents, versão instalada 2.1.286): arquivo `.md` com frontmatter YAML, só `name` e `description` obrigatórios, `tools` aceita string separada por vírgula ou lista YAML, `model` opcional (`sonnet`, `opus`, `haiku`, `fable`, id completo ou `inherit`), ferramentas MCP por nome exato (`mcp__ragx__build_context`). **Ponto que ficou em aberto:** a página diz que o `CLAUDE_CONFIG_DIR` NÃO muda o local `~/.claude/agents/` (fixo na home), mas a task manda instalar em `<perfil>/agents` (o diretório do `settings.json`), e foi o que implementei. No perfil padrão as duas coisas coincidem; nos perfis de `CLAUDE_CONFIG_DIR` o arquivo pode não ser enxergado pelo Claude Code. Não tenho como confirmar sem uma sessão com um perfil desses; quem usa vários perfis deve conferir se o `ragx-explorer` aparece na lista.
- Implementado: `clients/claude_agent.py` (texto como constante, marcador `<!-- ragx:managed v1 -->` logo após o frontmatter, `install_agent/remove_agent/has_agent` com `_backup` e `_escrever` do registry), `ragx claude agent install|remove|status [--profile] [--dry-run] [--json]`, `ragx claude on --agent/--no-agent` (padrão desligado), `off` remove o nosso, `agent` em `claude status --json`. O teste de frontmatter pegou um bug real: a `description` tinha um `: ` e quebrava o YAML; agora ela vai entre aspas (JSON é YAML válido) e o texto não tem o `: `. Testes em `tests/unit/test_claude_agent.py` (13: frontmatter, ≤ 60 tokens, ferramentas contra `build_server` nos dois perfis, idempotência, dry-run, arquivo alheio, versão antiga, remove, vários perfis, on/off, status).
- Reinstalar reescreve o arquivo (com backup `.ragx-backup-*`): quem acrescentou `model:` precisa refazer. A `docs/14-cli.md` diz isso.
- Nada medido sobre economia: só o A/B da 0162 diz.
