# RAGX-0158 — `instructions` ≤ 2 KB, descrições para Tool Search e lista estável

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.1, 7.2 #2) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T4, S2) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `done` |

## Objetivo

O Claude Code trunca as `instructions` do servidor em ~2 KB, descobre ferramentas por Tool Search (que lê nome e descrição) e perde o cache de prompt quando a lista de ferramentas muda. Hoje as `instructions` têm **531 bytes (~130 tokens)** e já cabem, mas citam `get_playbook`, que não existe no perfil `slim` (0157), e nada impede que cresçam ou que uma descrição mude sem querer. Esta tarefa fixa o teto, adapta o texto ao perfil e deixa a lista estável por teste.

## Entregáveis

- [x] **Medir primeiro:** bytes e tokens de `short_instructions(...) + " " + _ORDER_HINT` (`mcp/playbook.py:128-141`, `mcp/server.py:131-135`) em `full`/`slim` × escrita ligada/desligada, e tokens de cada descrição de ferramenta. Registrar em Medição.
- [x] `short_instructions(write_enabled, profile)` (playbook.py:128): o texto só cita ferramentas que existem naquele perfil. No `slim`: sem `get_playbook`; traz o essencial que o playbook ensinava (ordem `get_dictionary` → `search_hybrid` → `build_context` → `get_chunk`, `refresh` no início da tarefa, o índice não contém segredo).
- [x] Mover `_ORDER_HINT` (server.py:131-135) para `playbook.py`, junto do resto do texto; `build_server` (server.py:584-587) só chama a função.
- [x] Descrições das 33 ferramentas reescritas: o que faz + quando usar + os termos que o modelo usaria ao procurá-la ("localizar", "onde", "quem chama", "reindexar"). Verbo no início, **≤ 200 caracteres**, sem valor que mude (contagem, nome do projeto, data).
- [x] Lista estável: ordem de registro fixa e nada em `list_tools()` ou nas `instructions` depende de estado da sessão. Teste-ouro: `tests/fixtures/mcp_tools_full.json` e `mcp_tools_slim.json` com o `list_tools()` serializado; mudar uma descrição passa a exigir regravar o arquivo de propósito.
- [x] `docs/09-mcp.md`: parágrafo "Como escrever a descrição de uma ferramenta" e "a lista é estável" (por quê: cache de prompt e Tool Search). CHANGELOG.

## Fora de escopo

- Schemas de entrada e o conjunto de ferramentas (0157). Tamanho das respostas (0155). O texto do hint de SessionStart (0164).
- Enxugar o conteúdo de `get_playbook` (885 tokens, sob demanda; `docs/09-mcp.md` o descreve) e renomear qualquer ferramenta.
- Medir o efeito real no Tool Search do Claude Code: não há como automatizar aqui; entra no A/B (0162).

## Critérios de aceite

- [x] `instructions` ≤ **2.048 bytes UTF-8** em todas as combinações de perfil e escrita, e sem citar ferramenta que o perfil não expõe.
- [x] Toda descrição ≤ 200 caracteres e começando por verbo.
- [x] `list_tools()` chamado duas vezes devolve JSON idêntico e igual ao arquivo-ouro, nos dois perfis.
- [x] S2 (`slim` ≤ 600 tokens, da 0157) continua verdadeiro depois de reescrever as descrições.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `instructions`, bytes (`full`, escrita ligada) | 531 | **531** (`full` leitura 365; `slim` 356 / 289) |
| `instructions`, tokens | ~130 (auditoria) | ~130 (`full`), ~90 (`slim`) |
| Custo fixo `slim` (S2), tokens | 355 (0157) | **370** (≤ 600 ✓); `full`: 2.575 → 2.680 (+4%, descrições mais informativas) |
| Maior descrição, caracteres | 169 (`refresh`) | **141** (todas ≤ 200 e com verbo no início) |

Comando: `uv run ragx mcp tools --profile slim --json` e `uv run python scripts/medir_fio.py --tool tools_list`.

## Testes

- [x] `tests/integration/test_mcp_estavel.py` (novo): teto de 2.048 bytes por perfil×escrita; nenhum nome de ferramenta ausente do perfil citado nas `instructions`; descrições ≤ 200 chars; duas chamadas de `list_tools()` idênticas; comparação com o arquivo-ouro (a mensagem de falha diz como regravar). **A comparação com o ouro falha se alguém mexer numa descrição sem querer.**
- [x] `tests/integration/test_mcp.py::test_playbook_ensina_a_ordem_e_os_limites` (linha 369) segue verde.
- [x] `tests/unit/test_documentacao_mcp.py` segue verde (nomes não mudam).
- [x] Teste arquitetural "MCP é casca fina": `playbook.py` continua sem `os`/`open` (o texto fica em Python, de propósito, ver o docstring do módulo).

## Notas

- **Premissa já cumprida:** o teto de 2 KB não é violado hoje (531 B medidos nesta rodada). O valor da tarefa é a trava e a adaptação ao `slim`, não cortar texto. Não inventar cortes para "ganhar" bytes.
- Troca de perfil muda a lista **entre sessões**, não dentro de uma (o servidor lê `cfg.mcp.profile` uma vez em `build_server`); isso é estável no sentido que importa para o cache.
- O Tool Search do Claude Code não tem algoritmo documentado aqui: tratar "termos do modelo no texto da descrição" como hipótese, e deixar a conferência manual (`ToolSearch "localizar código"` achando `search_hybrid`) em uma sessão real como item opcional em Andamento.
- Confirmado em `mcp/playbook.py:128-141` (a frase "Comece por get_playbook (uma vez)" é a que quebra no `slim`) e `server.py:584-587`.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0158)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: as 33 descrições reescritas (verbo no início, termos de quem procura, ≤ 200 caracteres), `short_instructions(write_enabled, profile)` com a ordem por perfil dentro de `playbook.py` (`_ORDER_HINT` saiu do `server.py`) e `INSTRUCTIONS_MAX_BYTES = 2048`, descrições do `slim` também com verbo, e os arquivos-ouro `tests/fixtures/mcp_tools_full.json` / `mcp_tools_slim.json` (regravar: `RAGX_REGRAVAR_OURO=1`). Testes em `tests/integration/test_mcp_estavel.py` (11).
- O texto do `full` não foi cortado (a nota da task diz para não inventar cortes): continua em 531 bytes. O custo das descrições mais informativas foi +105 tokens no `full` e +15 no `slim`.
- Opcional, não feito (precisa de uma sessão real): conferir que `ToolSearch "localizar código"` acha `search_hybrid` e `"quem chama"` acha `get_entity`; é hipótese sobre o Tool Search do Claude Code, que não tem algoritmo documentado aqui. Entra no A/B da 0162.
