# Documentação — RAGX

Knowledge Engine local para projetos de software: indexa um repositório, protege segredos,
responde busca híbrida, monta contexto para agentes e expõe tudo via MCP.

> **Stack:** Python 3.11+ · SQLite · CLI `rag` · MCP stdio
> **Princípio nº 1:** nenhum segredo entra na base de conhecimento. Nunca.
> **Princípio nº 2:** o conhecimento versionado nunca estoura o limite do Git.
> **Princípio nº 3:** conhecimento de vários projetos se comunica, sem servidor central.

## Mapa da documentação

| Doc | Assunto | Fase |
|-----|---------|------|
| [00 — Visão geral](00-visao-geral.md) | Problema, objetivos, não-objetivos, glossário | — |
| [01 — Arquitetura](01-arquitetura.md) | Camadas, componentes, fluxos, stack | — |
| [02 — Segurança](02-seguranca.md) | IgnoreEngine, SecurityScanner, Security Gate | 0 |
| [03 — Modelo de dados](03-modelo-de-dados.md) | Schema SQLite, migrações, IDs determinísticos | 0–3 |
| [04 — Indexação](04-indexacao.md) | Walker, parsers, chunking, incremental | 1 |
| [05 — Busca](05-busca.md) | Semântica, keyword, híbrida, fusão, ranking | 2 |
| [06 — Grafo de conhecimento](06-grafo.md) | Entidades, relações, graph search | 3 |
| [07 — Context Engine](07-context-engine.md) | Expansão, dedup, compressão, token budget | 4 |
| [08 — Knowledge Dictionary](08-dictionary.md) | dictionary.json, glossário, sumários | 5 |
| [09 — MCP](09-mcp.md) | Ferramentas, contratos, fronteira de segurança | 6 |
| [10 — Agent Training](10-agent-training.md) | Perfis de agente, skills, rules, avaliação | 7 |
| [11 — Export / Import](11-export-import.md) | Pacote `.rag`, manifest, integridade | 8 |
| [12 — Git Sync](12-git-sync.md) | Conhecimento versionável, sync incremental, merge | 9 |
| [13 — Testes e Hardening](13-testes-hardening.md) | Pirâmide de testes, fixture de segredos, release | 10 |
| [14 — CLI](14-cli.md) | Referência de todos os comandos | todas |
| [15 — Configuração](15-configuracao.md) | `ragx.toml`, env vars, perfis | todas |
| [16 — Orçamento de tamanho](16-orcamento-de-tamanho.md) | Limites do Git, quantização, sharding | 1, 9 |
| [17 — Multiprojeto e federação](17-multiprojeto-e-federacao.md) | Hub, fatia pública, consulta cross-project | 11 |
| [18 — Conhecimento base](18-conhecimento-base.md) | Fontes externas, `@base/`, opt-in por projeto | 11 |
| [19 — Watch e autonomia do agente](19-watch-e-autonomia-do-agente.md) | `ragx watch`, escrita via MCP, playbook | 11 |
| [20 — Task Analyzer](20-task-analyzer.md) | Classificar a solicitação: executar ou documentar antes | 13 |
| [21 — Orquestração de tarefas](21-orquestracao-de-tarefas.md) | SQLite, DAG, lease, retry, scheduler, worker | 13 |
| [Roadmap](roadmap.md) | Fases, dependências, critérios de aceite | todas |
| [ADRs](adr/) | Decisões arquiteturais registradas | — |

## Como ler

1. Comece por [00 — Visão geral](00-visao-geral.md) e [01 — Arquitetura](01-arquitetura.md).
2. Antes de escrever qualquer linha de código, leia [02 — Segurança](02-seguranca.md).
   É a única parte do sistema que não admite atalho.
3. Leia [16 — Orçamento de tamanho](16-orcamento-de-tamanho.md) antes de decidir o que
   gravar em `knowledge/`. O teto do Git é restrição de projeto, não ajuste posterior.
4. Para implementar, siga o [Roadmap](roadmap.md) e o board em [`../task/`](../task/).

## Estado atual

As 14 fases estão implementadas. O RAGX indexa a si mesmo: 301 documentos,
2.355 chunks, 1.364 entidades, 6.009 relações, `knowledge/` em 4,2 MB.

Uma ressalva honesta, medida e documentada em [05 — Busca](05-busca.md): com um
embedder real, a busca híbrida ainda **não** supera a busca por palavra-chave no
conjunto de avaliação (recall@5 de 0,65 contra 0,77). O critério documentado
`híbrida > semântica > keyword` não foi atingido, e a análise do porquê está
naquele documento. Trate a busca como auxílio à descoberta, não como fonte
única de verdade.
