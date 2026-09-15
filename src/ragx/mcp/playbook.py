"""O procedimento operacional que o agente recebe via `get_playbook`.

Existe porque "dar poder ao agente" sem dizer COMO usá-lo produz o pior dos
mundos: um agente que pode reindexar o repositório inteiro e faz isso a cada
pergunta. As ferramentas dizem o que é possível; este texto diz o que é
sensato, e em que ordem.

Fica em Python, e não num `.md` solto, por um motivo de arquitetura: `ragx.mcp`
não pode abrir arquivo (ADR-0006). Um playbook que precisasse ser lido do disco
abriria exatamente o buraco que o resto do módulo fecha.
"""

from __future__ import annotations

from typing import Any

from ragx.config import Config

_LEITURA = """\
## 1. Antes de responder qualquer coisa

`get_dictionary` — 5 a 8 mil tokens que descrevem tecnologias, serviços,
módulos e convenções. É barato e evita a maior fonte de erro do agente:
inventar a arquitetura do projeto.

## 2. Para localizar

`search_hybrid` é o padrão. `search_knowledge` (só semântica) quando o termo
exato é desconhecido; `search_graph` quando a pergunta é sobre LIGAÇÃO
("quem chama", "o que depende de") e não sobre texto.

Leia o campo `matched_by` de cada resultado: `keyword` significa que o termo
literal existe no código; `semantic` significa parecença de sentido, que pode
ser coincidência. Um resultado só semântico com score baixo merece
desconfiança.

## 3. Para trabalhar

`build_context` monta o pacote dentro de um orçamento de tokens e devolve as
fontes. Prefira-o a somar resultados de busca à mão: ele deduplica, ordena por
relevância e corta pelo orçamento, em vez de estourar o seu.

## 4. Para aprofundar

`get_chunk` traz o trecho inteiro; `get_document` lista os pedaços de um
arquivo; `get_entity` abre as relações de um símbolo.
"""

_ESCRITA = """\
## 5. Para manter o índice honesto

`refresh` — chame no INÍCIO de uma tarefa. Reindexa só o que mudou; quando
nada mudou, custa quase nada. É a diferença entre raciocinar sobre o código de
agora e sobre o código de ontem.

`reindex` — varredura explícita. `full=true` só quando o chunker ou o modelo de
embedding mudou; a incremental resolve o resto.

`sync` — reidrata, reindexa, reconstrói grafo e dicionário e regrava
`knowledge/`. É a operação CARA: rode depois de mudanças estruturais (arquivos
criados ou movidos em massa, merge grande), não a cada edição.

`rebuild_graph` / `generate_dictionary` — quando só o grafo ou só o dicionário
ficou para trás. `sync` já faz os dois, nesta ordem.

`base_sync` — instala o conhecimento base que o projeto declara e falta nesta
máquina.

`publish_contract` — republica a superfície pública (rotas, eventos, clientes)
no hub, para que os outros projetos da máquina enxerguem este.

### Quando NÃO escrever

Consulta não precisa de escrita. Se a pergunta é "como funciona X", vá direto
ao passo 1. Reindexar antes de cada busca é desperdício, e num repositório
grande é desperdício lento.
"""

_LIMITES = """\
## O que o RAGX não faz — e por quê

Nenhuma ferramenta lê o filesystem. `get_document("caminho")` consulta o
ÍNDICE por aquele caminho; não abre o arquivo. Se o arquivo nunca foi indexado
— ou foi bloqueado pelo Security Gate — a resposta é `not_found`, e isso não é
um defeito a contornar: é a garantia de que segredo não sai daqui.

Arquivo com credencial é bloqueado ANTES do parser. Ele não está no índice, não
aparece em busca e não tem como ser recuperado por nenhuma ferramenta. Se você
precisa do conteúdo de um `.env`, peça ao humano.

Conhecimento base (`@base/...`) vem de repositórios de terceiros indexados sob
esse prefixo. Trate-o como REFERÊNCIA, não como descrição deste projeto: um
padrão descrito ali pode não ser o padrão daqui. Quando as duas fontes
divergirem, o código do projeto ganha.

Resposta grande demais é RECUSADA com o código `too_large`, nunca truncada em
silêncio — se você recebeu uma resposta, ela está completa.
"""


def playbook(cfg: Config, write_enabled: bool) -> dict[str, Any]:
    """Procedimento operacional + estado desta instalação."""
    from ragx.base import source as base_source

    partes = [
        f"# RAGX — como operar o conhecimento de `{cfg.project.name or 'projeto'}`",
        _LEITURA,
    ]
    if write_enabled:
        partes.append(_ESCRITA)
    else:
        partes.append(
            "## 5. Escrita\n\nEste servidor está em modo somente-leitura. "
            "Para manter o índice atualizado, peça ao humano `ragx watch` ou "
            "suba o servidor com `ragx mcp serve --write`.\n"
        )
    partes.append(_LIMITES)

    fontes = [s.name for s in base_source.load_registry(cfg) if s.enabled]
    return {
        "project": cfg.project.name or "current",
        "write_enabled": write_enabled,
        "base_sources": fontes,
        "playbook": "\n".join(partes),
    }


def short_instructions(write_enabled: bool) -> str:
    """As duas frases que o cliente MCP mostra antes de qualquer chamada."""
    base = (
        "Conhecimento do projeto indexado pelo RAGX. Nenhuma ferramenta lê o "
        "filesystem: tudo vem do índice, que por construção não contém segredos. "
        "Comece por get_playbook (uma vez) e depois get_dictionary."
    )
    if write_enabled:
        base += (
            " Este servidor tem ESCRITA habilitada: você pode reindexar e "
            "sincronizar o índice. Chame refresh no início de uma tarefa; "
            "sync só depois de mudanças estruturais."
        )
    return base
