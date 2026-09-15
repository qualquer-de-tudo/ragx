# RAGX-0002 — Configuração: ragx.toml, env vars e precedência

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0001` |
| **Bloqueia** | `RAGX-0004`, `RAGX-0005` |
| **Documentação** | [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

Implementar a cascata de configuração completa e a descoberta da raiz do projeto.

## Entregáveis

- [ ] `config.py` com modelos pydantic-settings para todas as seções de `docs/15-configuracao.md`
- [ ] Precedência: flags CLI > `RAGX_*` > `ragx.toml` do projeto > config do usuário > defaults
- [ ] Descoberta da raiz: sobe do cwd até achar `ragx.toml`; sem ele, usa cwd e avisa
- [ ] Mapeamento `RAGX_<SECAO>_<CHAVE>`; `OLLAMA_HOST` como fallback de `embedding.base_url`
- [ ] `ragx config show|get|set` com validação

## Fora de escopo

- Leitura de credenciais de API a partir do TOML — proibido por design

## Critérios de aceite

- [ ] Todas as seções do doc 15 são carregáveis e validadas
- [ ] Valor inválido produz erro acionável citando chave e valores aceitos (exit 2)
- [ ] Precedência comprovada por teste para cada um dos 5 níveis
- [ ] Nenhuma chave de credencial é lida do TOML

## Testes

- [ ] Unitário por nível de precedência
- [ ] Descoberta de raiz em subdiretório aninhado

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
