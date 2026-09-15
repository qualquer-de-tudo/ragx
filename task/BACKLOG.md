# Backlog — RAGX

Índice de todas as tarefas, na ordem de execução. Detalhes de cada uma no arquivo
correspondente; regras do board em [README.md](README.md); plano geral em
[../docs/roadmap.md](../docs/roadmap.md).

## Resumo

| Fase | Nome | Prioridade | Tarefas | Esforço |
|------|------|-----------|---------|---------|
| **0** | [Fundação + Security Gate](fase-00-fundacao-seguranca/) | 🔴 obrigatória | 11 | ~8d |
| **1** | [Indexer + Knowledge Store](fase-01-indexacao/) | 🔴 obrigatória | 14 | ~9,75d |
| **2** | [Semantic + Hybrid Search](fase-02-busca/) | 🔴 obrigatória | 9 | ~4,75d |
| **3** | [Graph Knowledge](fase-03-grafo/) | 🟠 alta | 6 | ~4,5d |
| **4** | [Context Engine](fase-04-context-engine/) | 🔴 obrigatória para agentes | 5 | ~3,5d |
| **5** | [Knowledge Dictionary](fase-05-dictionary/) | 🟠 alta | 3 | ~2d |
| **6** | [MCP](fase-06-mcp/) | 🔴 obrigatória | 4 | ~2,5d |
| **7** | [Agent Knowledge Training](fase-07-agent-training/) | 🟠 alta | 5 | ~4d |
| **8** | [Export / Import (.rag)](fase-08-export-import/) | 🟠 alta | 4 | ~2,75d |
| **9** | [Git Sync / Merge](fase-09-git-sync/) | 🔴 obrigatória para time | 4 | ~4d |
| **10** | [Hardening + Release](fase-10-hardening/) | 🔴 obrigatória | 6 | ~3,5d |
| **11** | [Multiprojeto + Federação](fase-11-multiprojeto-federacao/) | 🔴 obrigatória p/ microsserviços | 9 | ~8,5d |
| | **Total** | | **80** | **~57,75d** |

> Estimativas são ordem de grandeza para um desenvolvedor, não compromisso de prazo.

## Fase 0 — Fundação + Security Gate

Base do projeto e barreira de segurança. Nada avança enquanto a suíte de segredos não estiver verde.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0001](fase-00-fundacao-seguranca/RAGX-0001-bootstrap-do-projeto-python.md) | Bootstrap do projeto Python | P0 | 0,5d | — | `todo` |
| [RAGX-0002](fase-00-fundacao-seguranca/RAGX-0002-configuracao-ragx-toml-env-vars-e-precedencia.md) | Configuração: ragx.toml, env vars e precedência | P0 | 0,5d | RAGX-0001 | `todo` |
| [RAGX-0003](fase-00-fundacao-seguranca/RAGX-0003-camada-de-storage-conexao-pragmas-e-migracoes.md) | Camada de storage: conexão, pragmas e migrações | P0 | 0,5d | RAGX-0001 | `todo` |
| [RAGX-0004](fase-00-fundacao-seguranca/RAGX-0004-ignoreengine.md) | IgnoreEngine | P0 | 1d | RAGX-0002 | `todo` |
| [RAGX-0005](fase-00-fundacao-seguranca/RAGX-0005-securityscanner-fase-1-deny-list-por-nome-de-arquivo.md) | SecurityScanner — fase 1: deny-list por nome de arquivo | P0 | 0,5d | RAGX-0002 | `todo` |
| [RAGX-0006](fase-00-fundacao-seguranca/RAGX-0006-securityscanner-fase-2-deteccao-de-segredo-em-conteudo.md) | SecurityScanner — fase 2: detecção de segredo em conteúdo | P0 | 1,5d | RAGX-0005 | `todo` |
| [RAGX-0007](fase-00-fundacao-seguranca/RAGX-0007-redactor-e-persistencia-de-securityevent.md) | Redactor e persistência de SecurityEvent | P0 | 0,5d | RAGX-0006, RAGX-0003 | `todo` |
| [RAGX-0008](fase-00-fundacao-seguranca/RAGX-0008-securitygate-fachada-e-invariante-arquitetural.md) | SecurityGate: fachada e invariante arquitetural | P0 | 0,5d | RAGX-0004, RAGX-0007 | `todo` |
| [RAGX-0009](fase-00-fundacao-seguranca/RAGX-0009-cli-da-fase-0-init-doctor-security-scan-security-rules.md) | CLI da Fase 0: init, doctor, security scan, security rules | P0 | 1d | RAGX-0008, RAGX-0003 | `todo` |
| [RAGX-0010](fase-00-fundacao-seguranca/RAGX-0010-fixture-de-segredos-e-suite-das-cinco-superficies.md) | Fixture de segredos e suíte das cinco superfícies | P0 | 1d | RAGX-0009 | `todo` |
| [RAGX-0011](fase-00-fundacao-seguranca/RAGX-0011-pipeline-de-ci-em-linux-e-windows.md) | Pipeline de CI em Linux e Windows | P1 | 0,5d | RAGX-0010 | `todo` |

## Fase 1 — Indexer + Knowledge Store

O sistema passa a entender projetos: walker, parsers, chunkers, indexação incremental.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0012](fase-01-indexacao/RAGX-0012-modelos-de-dominio-e-ids-deterministicos.md) | Modelos de domínio e IDs determinísticos | P0 | 0,5d | RAGX-0010 | `todo` |
| [RAGX-0013](fase-01-indexacao/RAGX-0013-filewalker.md) | FileWalker | P0 | 1d | RAGX-0012 | `todo` |
| [RAGX-0014](fase-01-indexacao/RAGX-0014-migracao-e-repositorios-de-documents-chunks-fts5.md) | Migração e repositórios de documents/chunks/FTS5 | P0 | 0,5d | RAGX-0012, RAGX-0003 | `todo` |
| [RAGX-0015](fase-01-indexacao/RAGX-0015-parser-de-markdown-e-texto.md) | Parser de Markdown e texto | P0 | 0,5d | RAGX-0012 | `todo` |
| [RAGX-0016](fase-01-indexacao/RAGX-0016-parser-de-python-via-ast.md) | Parser de Python via ast | P0 | 0,5d | RAGX-0012 | `todo` |
| [RAGX-0017](fase-01-indexacao/RAGX-0017-parser-tree-sitter-para-php-js-ts-e-tsx.md) | Parser tree-sitter para PHP, JS, TS e TSX | P0 | 1d | RAGX-0016 | `todo` |
| [RAGX-0018](fase-01-indexacao/RAGX-0018-parsers-de-json-yaml-xml-e-sql.md) | Parsers de JSON, YAML, XML e SQL | P1 | 0,5d | RAGX-0012 | `todo` |
| [RAGX-0019](fase-01-indexacao/RAGX-0019-chunker-de-codigo.md) | Chunker de código | P0 | 1d | RAGX-0016, RAGX-0017 | `todo` |
| [RAGX-0020](fase-01-indexacao/RAGX-0020-chunker-de-documentacao-e-fallback.md) | Chunker de documentação e fallback | P0 | 0,5d | RAGX-0015 | `todo` |
| [RAGX-0021](fase-01-indexacao/RAGX-0021-pipeline-de-indexacao-incremental.md) | Pipeline de indexação incremental | P0 | 1,5d | RAGX-0013, RAGX-0014, RAGX-0019, RAGX-0020, RAGX-0008 | `todo` |
| [RAGX-0022](fase-01-indexacao/RAGX-0022-cli-de-indexacao-e-inspecao.md) | CLI de indexação e inspeção | P0 | 0,5d | RAGX-0021 | `todo` |
| [RAGX-0023](fase-01-indexacao/RAGX-0023-determinismo-de-ids-entre-plataformas.md) | Determinismo de IDs entre plataformas | P0 | 0,5d | RAGX-0021, RAGX-0011 | `todo` |
| [RAGX-0069](fase-01-indexacao/RAGX-0069-identidade-de-projeto.md) | Identidade de projeto | P0 | 0,25d | RAGX-0014 | `todo` |
| [RAGX-0070](fase-01-indexacao/RAGX-0070-orcamento-de-tamanho-contagem-projecao-e-recusa.md) | Orçamento de tamanho: contagem, projeção e recusa | P0 | 1d | RAGX-0014 | `todo` |

## Fase 2 — Semantic + Hybrid Search

Fim do MVP vertical: init → index → search funcionando com proteção contra segredos.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0024](fase-02-busca/RAGX-0024-embedder-protocol-cache-e-provider-de-hashing.md) | Embedder Protocol, cache e provider de hashing | P0 | 0,5d | RAGX-0021 | `todo` |
| [RAGX-0025](fase-02-busca/RAGX-0025-provider-ollama-nomic-embed-text.md) | Provider Ollama (nomic-embed-text) | P0 | 0,5d | RAGX-0024 | `todo` |
| [RAGX-0026](fase-02-busca/RAGX-0026-provider-fastembed-fallback-sem-daemon.md) | Provider fastembed (fallback sem daemon) | P1 | 0,25d | RAGX-0024 | `todo` |
| [RAGX-0027](fase-02-busca/RAGX-0027-busca-semantica-com-vectorindex-numpy.md) | Busca semântica com VectorIndex NumPy | P0 | 0,5d | RAGX-0025 | `todo` |
| [RAGX-0028](fase-02-busca/RAGX-0028-busca-keyword-fts5-e-preparacao-de-query.md) | Busca keyword FTS5 e preparação de query | P0 | 0,5d | RAGX-0014 | `todo` |
| [RAGX-0029](fase-02-busca/RAGX-0029-fusao-hibrida-rrf-reranking-e-diversidade.md) | Fusão híbrida RRF, reranking e diversidade | P0 | 0,5d | RAGX-0027, RAGX-0028 | `todo` |
| [RAGX-0030](fase-02-busca/RAGX-0030-cli-de-busca.md) | CLI de busca | P0 | 0,5d | RAGX-0029 | `todo` |
| [RAGX-0031](fase-02-busca/RAGX-0031-conjunto-de-avaliacao-e-comando-rag-eval.md) | Conjunto de avaliação e comando ragx eval | P0 | 0,5d | RAGX-0030 | `todo` |
| [RAGX-0071](fase-02-busca/RAGX-0071-quantizacao-de-embeddings-e-busca-em-dois-estagios.md) | Quantização de embeddings e busca em dois estágios | P0 | 1d | RAGX-0027, RAGX-0070 | `todo` |

## Fase 3 — Graph Knowledge

Entidades e relações; consulta combinando vetor e grafo.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0032](fase-03-grafo/RAGX-0032-migracao-e-store-do-grafo.md) | Migração e store do grafo | P1 | 0,5d | RAGX-0021 | `todo` |
| [RAGX-0033](fase-03-grafo/RAGX-0033-extrator-estrutural-camada-1.md) | Extrator estrutural (camada 1) | P1 | 0,5d | RAGX-0032 | `todo` |
| [RAGX-0034](fase-03-grafo/RAGX-0034-extrator-referencial-e-catalogo-de-tecnologias-camada-2.md) | Extrator referencial e catálogo de tecnologias (camada 2) | P1 | 1d | RAGX-0033 | `todo` |
| [RAGX-0035](fase-03-grafo/RAGX-0035-travessia-e-graph-search-vetor-grafo.md) | Travessia e graph-search (vetor + grafo) | P1 | 1d | RAGX-0034, RAGX-0029 | `todo` |
| [RAGX-0036](fase-03-grafo/RAGX-0036-cli-do-grafo.md) | CLI do grafo | P1 | 0,5d | RAGX-0035 | `todo` |
| [RAGX-0037](fase-03-grafo/RAGX-0037-extrator-semantico-opt-in-camada-3.md) | Extrator semântico opt-in (camada 3) | P2 | 1d | RAGX-0036 | `todo` |

## Fase 4 — Context Engine

Contexto pronto dentro de um orçamento de tokens, sem duplicata e sem perder a fonte.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0038](fase-04-context-engine/RAGX-0038-tokencounter-e-alocador-de-orcamento.md) | TokenCounter e alocador de orçamento | P0 | 0,5d | RAGX-0030 | `todo` |
| [RAGX-0039](fase-04-context-engine/RAGX-0039-deduplicacao-literal-quase-duplicata-e-mmr.md) | Deduplicação: literal, quase-duplicata e MMR | P0 | 0,5d | RAGX-0038 | `todo` |
| [RAGX-0040](fase-04-context-engine/RAGX-0040-compressao-extrativa.md) | Compressão extrativa | P0 | 1d | RAGX-0039 | `todo` |
| [RAGX-0041](fase-04-context-engine/RAGX-0041-contextengine-orquestracao-intents-e-cache.md) | ContextEngine: orquestração, intents e cache | P0 | 1d | RAGX-0040, RAGX-0035 | `todo` |
| [RAGX-0042](fase-04-context-engine/RAGX-0042-cli-rag-context-com-explain.md) | CLI ragx context com --explain | P0 | 0,5d | RAGX-0041 | `todo` |

## Fase 5 — Knowledge Dictionary

Mapa barato do projeto, para o agente se orientar antes de gastar contexto.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0043](fase-05-dictionary/RAGX-0043-dictionary-builder-deterministico.md) | Dictionary builder determinístico | P1 | 1d | RAGX-0034 | `todo` |
| [RAGX-0044](fase-05-dictionary/RAGX-0044-enriquecimento-semantico-e-re-scan-de-seguranca-do-dicionario.md) | Enriquecimento semântico e re-scan de segurança do dicionário | P2 | 0,5d | RAGX-0043 | `todo` |
| [RAGX-0045](fase-05-dictionary/RAGX-0045-cli-do-dicionario-e-serializacao-estavel.md) | CLI do dicionário e serialização estável | P1 | 0,5d | RAGX-0043 | `todo` |

## Fase 6 — MCP

Casca fina sobre a API interna. Sem acesso a filesystem, sem lógica de negócio.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0046](fase-06-mcp/RAGX-0046-esqueleto-do-servidor-mcp-e-contratos.md) | Esqueleto do servidor MCP e contratos | P0 | 0,5d | RAGX-0042, RAGX-0045 | `todo` |
| [RAGX-0047](fase-06-mcp/RAGX-0047-as-oito-ferramentas-mcp.md) | As oito ferramentas MCP | P0 | 1d | RAGX-0046 | `todo` |
| [RAGX-0048](fase-06-mcp/RAGX-0048-limites-rate-limiting-e-logging-com-hash-de-query.md) | Limites, rate limiting e logging com hash de query | P0 | 0,5d | RAGX-0047 | `todo` |
| [RAGX-0049](fase-06-mcp/RAGX-0049-testes-arquiteturais-e-de-seguranca-do-mcp.md) | Testes arquiteturais e de segurança do MCP | P0 | 0,5d | RAGX-0048 | `todo` |

## Fase 7 — Agent Knowledge Training

Perfis de agente versionáveis: regras, skills, exemplos e avaliação.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0050](fase-07-agent-training/RAGX-0050-schema-de-perfil-de-agente-e-rag-agent-create.md) | Schema de perfil de agente e ragx agent create | P1 | 0,5d | RAGX-0049 | `todo` |
| [RAGX-0051](fase-07-agent-training/RAGX-0051-rag-agent-train.md) | ragx agent train | P1 | 1,5d | RAGX-0050 | `todo` |
| [RAGX-0052](fase-07-agent-training/RAGX-0052-skills-e-examples-com-promocao-manual.md) | Skills e examples com promoção manual | P2 | 1d | RAGX-0051 | `todo` |
| [RAGX-0053](fase-07-agent-training/RAGX-0053-rag-agent-eval.md) | ragx agent eval | P1 | 0,5d | RAGX-0051 | `todo` |
| [RAGX-0054](fase-07-agent-training/RAGX-0054-templates-de-perfil-e-export.md) | Templates de perfil e export | P2 | 0,5d | RAGX-0053 | `todo` |

## Fase 8 — Export / Import (.rag)

Conhecimento portátil, com re-scan de segurança obrigatório no export.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0055](fase-08-export-import/RAGX-0055-formato-rag-manifest-e-checksums.md) | Formato .rag: manifest e checksums | P1 | 0,5d | RAGX-0045 | `todo` |
| [RAGX-0056](fase-08-export-import/RAGX-0056-exporter-com-re-scan-e-verificacao-de-integridade.md) | Exporter com re-scan e verificação de integridade | P1 | 1d | RAGX-0055 | `todo` |
| [RAGX-0057](fase-08-export-import/RAGX-0057-importer-compatibilidade-zip-slip-e-merge.md) | Importer: compatibilidade, zip-slip e merge | P1 | 1d | RAGX-0056 | `todo` |
| [RAGX-0058](fase-08-export-import/RAGX-0058-cli-de-portabilidade.md) | CLI de portabilidade | P1 | 0,25d | RAGX-0057 | `todo` |

## Fase 9 — Git Sync / Merge

Conhecimento versionado em texto e sync incremental. Sem merge de SQLite.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0059](fase-09-git-sync/RAGX-0059-serializacao-de-knowledge-sem-conteudo-quantizada-e-shardada.md) | Serialização de knowledge/ sem conteúdo, quantizada e shardada | P0 | 1,5d | RAGX-0045, RAGX-0070, RAGX-0071 | `todo` |
| [RAGX-0060](fase-09-git-sync/RAGX-0060-reidratacao-de-conteudo-e-deteccao-de-delta.md) | Reidratação de conteúdo e detecção de delta | P0 | 1d | RAGX-0059 | `todo` |
| [RAGX-0061](fase-09-git-sync/RAGX-0061-rag-sync-e-resolucao-de-conflito.md) | ragx sync e resolução de conflito | P0 | 1d | RAGX-0060 | `todo` |
| [RAGX-0062](fase-09-git-sync/RAGX-0062-git-hooks-e-receita-de-ci.md) | Git hooks e receita de CI | P1 | 0,5d | RAGX-0061 | `todo` |

## Fase 10 — Hardening + Release

Robustez, performance, qualidade estática e release.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0063](fase-10-hardening/RAGX-0063-suite-de-robustez.md) | Suíte de robustez | P0 | 1d | RAGX-0062 | `todo` |
| [RAGX-0064](fase-10-hardening/RAGX-0064-guard-rails-de-performance.md) | Guard rails de performance | P0 | 0,5d | RAGX-0063 | `todo` |
| [RAGX-0065](fase-10-hardening/RAGX-0065-manutencao-vacuum-reset-e-doctor-full.md) | Manutenção: vacuum, reset e doctor --full | P1 | 0,5d | RAGX-0063 | `todo` |
| [RAGX-0066](fase-10-hardening/RAGX-0066-hardening-final-de-qualidade-estatica.md) | Hardening final de qualidade estática | P0 | 0,5d | RAGX-0064 | `todo` |
| [RAGX-0067](fase-10-hardening/RAGX-0067-empacotamento-e-release.md) | Empacotamento e release | P0 | 0,5d | RAGX-0066 | `todo` |
| [RAGX-0068](fase-10-hardening/RAGX-0068-revisao-de-documentacao-contra-o-comportamento-real.md) | Revisão de documentação contra o comportamento real | P0 | 0,5d | RAGX-0067 | `todo` |

## Fase 11 — Multiprojeto + Federação

Hub na máquina, fatia pública por projeto e consulta que cruza repositórios.

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|-----------|--------|
| [RAGX-0072](fase-11-multiprojeto-federacao/RAGX-0072-extracao-da-superficie-publica-provides-consumes.md) | Extração da superfície pública (provides / consumes) | P0 | 1,5d | RAGX-0034, RAGX-0069 | `todo` |
| [RAGX-0073](fase-11-multiprojeto-federacao/RAGX-0073-fatia-de-federacao-versionada.md) | Fatia de federação versionada | P0 | 1d | RAGX-0072 | `todo` |
| [RAGX-0074](fase-11-multiprojeto-federacao/RAGX-0074-hub-local-registro-de-projetos-e-sincronizacao.md) | Hub local: registro de projetos e sincronização | P0 | 1,5d | RAGX-0073, RAGX-0061 | `todo` |
| [RAGX-0075](fase-11-multiprojeto-federacao/RAGX-0075-resolucao-de-vinculos-entre-projetos.md) | Resolução de vínculos entre projetos | P0 | 1d | RAGX-0074 | `todo` |
| [RAGX-0076](fase-11-multiprojeto-federacao/RAGX-0076-busca-e-contexto-cross-project.md) | Busca e contexto cross-project | P0 | 1,5d | RAGX-0075, RAGX-0041 | `todo` |
| [RAGX-0077](fase-11-multiprojeto-federacao/RAGX-0077-mcp-multiprojeto.md) | MCP multiprojeto | P0 | 0,5d | RAGX-0076, RAGX-0049 | `todo` |
| [RAGX-0078](fase-11-multiprojeto-federacao/RAGX-0078-isolamento-de-seguranca-entre-projetos.md) | Isolamento de segurança entre projetos | P0 | 0,5d | RAGX-0077 | `todo` |
| [RAGX-0079](fase-11-multiprojeto-federacao/RAGX-0079-perfis-de-agente-com-escopo-multiprojeto.md) | Perfis de agente com escopo multiprojeto | P2 | 0,5d | RAGX-0078, RAGX-0051 | `todo` |
| [RAGX-0080](fase-11-multiprojeto-federacao/RAGX-0080-documentacao-e-receita-de-adocao-multiprojeto.md) | Documentação e receita de adoção multiprojeto | P1 | 0,5d | RAGX-0079 | `todo` |

### Fase 12 — Autonomia + Conhecimento base

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|------------|--------|
| [RAGX-0081](fase-12-autonomia-e-conhecimento-base/RAGX-0081-conhecimento-base-compartilhado.md) | Conhecimento base compartilhado entre projetos | P0 | 1,5d | RAGX-0073 | `done` |
| [RAGX-0082](fase-12-autonomia-e-conhecimento-base/RAGX-0082-watcher-de-arquivos.md) | Watcher: o índice acompanhando o working tree | P0 | 1d | RAGX-0012 | `done` |
| [RAGX-0083](fase-12-autonomia-e-conhecimento-base/RAGX-0083-escrita-no-indice-via-mcp.md) | Escrita no índice via MCP + playbook | P0 | 1d | RAGX-0082, RAGX-0044 | `done` |
| [RAGX-0084](fase-12-autonomia-e-conhecimento-base/RAGX-0084-base-de-agents-otimizada.md) | Base de conhecimento `agents`, otimizada | P1 | 1d | RAGX-0081 | `done` |
| [RAGX-0085](fase-12-autonomia-e-conhecimento-base/RAGX-0085-ragx-como-comando-primario.md) | `ragx` como comando primário | P2 | 0,5d | — | `done` |

### Fase 13 — Task Analyzer + Orquestração

| ID | Tarefa | Prio | Est. | Depende de | Status |
|----|--------|------|------|------------|--------|
| [RAGX-0086](fase-13-task-analyzer-orquestracao/RAGX-0086-banco-de-orquestracao.md) | Banco de orquestração | P0 | 1,5d | RAGX-0009 | `done` |
| [RAGX-0087](fase-13-task-analyzer-orquestracao/RAGX-0087-task-analyzer.md) | Task Analyzer — classificação por sinais | P0 | 1,5d | RAGX-0086, RAGX-0028 | `done` |
| [RAGX-0088](fase-13-task-analyzer-orquestracao/RAGX-0088-documentation-planner.md) | Documentation Planner | P0 | 1d | RAGX-0087, RAGX-0043 | `done` |
| [RAGX-0089](fase-13-task-analyzer-orquestracao/RAGX-0089-task-decomposer-e-dag.md) | Task Decomposer e DAG | P0 | 1,5d | RAGX-0088 | `done` |
| [RAGX-0090](fase-13-task-analyzer-orquestracao/RAGX-0090-lifecycle-lease-e-retry.md) | Lifecycle, lease e retry | P0 | 1d | RAGX-0089 | `done` |
| [RAGX-0091](fase-13-task-analyzer-orquestracao/RAGX-0091-dispatcher-contexto-e-validacao.md) | Dispatcher, contexto e validação | P0 | 1,5d | RAGX-0090, RAGX-0042 | `done` |
| [RAGX-0092](fase-13-task-analyzer-orquestracao/RAGX-0092-scheduler-worker-e-eventos.md) | Scheduler, worker e eventos | P0 | 1d | RAGX-0091 | `done` |
| [RAGX-0093](fase-13-task-analyzer-orquestracao/RAGX-0093-cli-task-worker-schedule.md) | CLI `ragx task`, `worker`, `schedule` | P1 | 1d | RAGX-0092 | `done` |
| [RAGX-0094](fase-13-task-analyzer-orquestracao/RAGX-0094-mcp-de-orquestracao.md) | MCP de orquestração | P0 | 0,5d | RAGX-0091, RAGX-0083 | `done` |
| [RAGX-0095](fase-13-task-analyzer-orquestracao/RAGX-0095-tarefas-versionadas-e-sync.md) | Tarefas versionadas e reidratação | P1 | 1d | RAGX-0089, RAGX-0061 | `done` |
| [RAGX-0096](fase-13-task-analyzer-orquestracao/RAGX-0096-testes-obrigatorios-e-demonstracao.md) | Testes obrigatórios e demonstração | P0 | 1,5d | RAGX-0093, RAGX-0094, RAGX-0095 | `done` |

## Marcos

| Marco | Alcançado em | O que passa a funcionar |
|-------|-------------|------------------------|
| **Security Gate** | `RAGX-0010` | Nenhum segredo entra no sistema; suíte das 5 superfícies ativa |
| **Índice** | `RAGX-0023` | `ragx index .` incremental e determinístico entre plataformas |
| **Orçamento de tamanho** | `RAGX-0070` | `knowledge/` nunca estoura o teto do Git; escrita recusada em vez de truncada |
| **Vetores versionáveis** | `RAGX-0071` | int8@256 — 24 MB por 100k chunks em vez de 293 MB |
| **MVP vertical** | `RAGX-0031` | `init → index → search` com busca híbrida avaliada |
| **Contexto para agentes** | `RAGX-0042` | `ragx context` dentro de orçamento de tokens |
| **Agentes conectados** | `RAGX-0049` | MCP servindo 8 ferramentas, sem acesso a filesystem |
| **Colaboração** | `RAGX-0062` | Conhecimento no Git + `ragx sync` incremental |
| **Release** | `RAGX-0068` | Instalável, documentado, sem `xfail` de segurança |
| **Multiprojeto** | `RAGX-0080` | `--scope all` cruzando repositórios, com ou sem eles clonados |
| **Índice autônomo** | `RAGX-0083` | `ragx watch` + escrita via MCP: o agente mantém o próprio conhecimento fresco |
| **Conhecimento base** | `RAGX-0084` | Regras compartilhadas em `@base/`, uma cópia por máquina, receita no Git |
| **Trabalho orquestrado** | `RAGX-0096` | Pedido vira análise, documentação, tarefas com DAG, fila com lease e validação determinística |

