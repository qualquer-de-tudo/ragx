# 00 — Visão geral

## O problema

Um agente de IA que trabalha em um repositório real precisa responder perguntas como
"onde fica a autenticação?", "quais serviços falam com o Redis?", "qual é o padrão de
repositório aqui?". Hoje isso é resolvido de três formas ruins:

1. **Jogar o repositório inteiro no contexto** — caro, lento e quase sempre estoura o limite.
2. **Deixar o agente ler arquivos sob demanda** — ele lê `.env`, `credentials.json`,
   `id_rsa`, e o segredo vaza para o log, para o provedor do modelo e para o histórico.
3. **RAG genérico de documentos** — trata código como texto puro, perde estrutura
   (classe → método), perde relação (serviço → dependência) e devolve trechos truncados.

## O que o RAGX é

Um **Knowledge Engine local** que transforma um projeto em conhecimento consultável:

```text
repositório  →  [Security Gate]  →  conhecimento  →  agentes
```

- **Local-first.** Tudo em SQLite dentro do próprio projeto. Sem serviço externo obrigatório.
- **Seguro por construção.** O gate de segurança fica *antes* do parser, não depois do índice.
- **Consciente de código.** Chunking por estrutura sintática, não por janela de caracteres.
- **Relacional.** Além de vetores, um grafo de entidades e relações.
- **Orçado.** O Context Engine entrega contexto dentro de um limite de tokens.
- **Portátil.** Conhecimento exportável (`.rag`) e versionável no Git, sempre dentro
  de um orçamento de tamanho que o Git aceita.
- **Federado.** Cada projeto publica sua superfície pública; um hub na máquina do dev
  cruza vários projetos, para que APIs e microsserviços se enxerguem.
- **Integrável.** Servidor MCP como camada fina sobre a API interna.

## Objetivos

| # | Objetivo | Como medimos |
|---|----------|--------------|
| O1 | Nenhum segredo indexado, embarcado, grafado, servido ou exportado | Suíte de segurança: 0 ocorrências em 5 superfícies |
| O2 | Indexação incremental de um repo médio (~5k arquivos) | Reindexação sem mudanças < 5 s |
| O3 | Busca híbrida melhor que keyword puro | Recall@5 medido em conjunto de avaliação próprio |
| O4 | Contexto útil dentro de orçamento | 10k tokens recuperados → ≤ 3k entregues, sem perder os trechos-chave |
| O5 | Consumo por agentes sem acoplamento | Agente externo usa só ferramentas MCP |
| O6 | Colaboração via Git sem merge de binário | `git pull && ragx sync` atualiza só o delta |
| O7 | Conhecimento versionado dentro do limite do Git | 100k chunks < 50 MB em `knowledge/`; nenhum artefato > 20 MB |
| O8 | Pergunta que cruza repositórios | Agente em `order-service` obtém o contrato servido por `payment-service` sem tê-lo clonado |

## Não-objetivos (do MVP)

- Não é um banco vetorial distribuído. Um projeto = um SQLite; o hub multiprojeto é
  **local da máquina**, não um servidor.
- Não é um serviço multiusuário com autenticação e RBAC.
- Não faz *fine-tuning* de modelo. "Agent Training" aqui é **curadoria de conhecimento**
  (ver [10 — Agent Training](10-agent-training.md)), não gradient descent.
- Não tenta suportar 50 linguagens no MVP. Ver a lista fechada em [04 — Indexação](04-indexacao.md).
- Não é um chat. O RAGX entrega contexto; quem gera resposta é o agente.

## Personas

| Persona | Usa via | Precisa de |
|---------|---------|------------|
| **Dev individual** | CLI `rag` | `ragx index .` + `ragx search "..."` em segundos |
| **Agente de IA** | MCP | `build_context`, `search_hybrid`, `get_dictionary` |
| **Time** | Git + `.rag` | conhecimento versionado, `ragx sync` no pull |
| **Security/Compliance** | CLI + relatórios | prova auditável de que segredo nenhum foi indexado |

## Glossário

| Termo | Definição |
|-------|-----------|
| **Documento** | Um arquivo aceito pelo gate e parseado. Unidade de origem. |
| **Chunk** | Fatia semanticamente coerente de um documento (método, seção, bloco). Unidade de recuperação. |
| **Embedding** | Vetor denso de um chunk, produzido por um provider configurado. |
| **Entidade** | Nó do grafo: arquivo, classe, função, serviço, tecnologia, conceito. |
| **Relação** | Aresta tipada entre entidades (`uses`, `calls`, `documented_by`, ...). |
| **Security Gate** | Barreira obrigatória entre filesystem e qualquer persistência. |
| **Context Pack** | Saída do Context Engine: texto com fontes, dentro de um orçamento de tokens. |
| **Dictionary** | Resumo estruturado do projeto (tecnologias, serviços, conceitos) para orientação barata. |
| **Perfil de agente** | Pasta `agents/<nome>/` com instruções, regras, skills, exemplos e avaliação. |
| **Pacote `.rag`** | Arquivo portátil com conhecimento derivado, sem código-fonte bruto sensível. |
| **Hub** | Base local da máquina (`~/.ragx/hub/`) que agrega vários projetos e responde consultas cross-project. Derivado, nunca versionado. |
| **Fatia de federação** | `knowledge/federation/` — a superfície pública do projeto (endpoints, eventos, contratos), versionada e autossuficiente. |
| **Reidratação** | Reconstrução do conteúdo de um chunk a partir do working tree, usando caminho + intervalo de linhas, conferida por hash. |

## Princípios de design

1. **Security-first, não security-later.** O gate é a primeira coisa construída (Fase 0)
   e todo componente novo precisa provar que passa por ele.
2. **Determinismo.** Mesmo input + mesma versão do chunker = mesmos IDs. Sem isso não
   existe indexação incremental nem merge no Git.
3. **Fatiamento vertical.** Fase 0→2 já entrega um RAG funcional ponta a ponta
   (`init` → `index` → `search`). Infraestrutura sem produto é dívida.
4. **Uma fonte de verdade.** SQLite local é derivável; os artefatos versionados em
   `knowledge/` é que são a fonte compartilhada.
5. **MCP é casca fina.** Zero lógica de negócio e zero acesso a filesystem na camada MCP.
6. **Nada redundante vai para o Git.** Conteúdo de chunk é derivável do próprio
   repositório, então não é versionado — é reidratado e conferido por hash
   ([ADR-0010](adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md)).
7. **Fluxo unidirecional entre camadas.** working tree → `.ragx/` → `knowledge/` →
   `federation/` → hub. Nada volta, e toda camada acima é descartável.
