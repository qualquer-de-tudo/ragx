"""Isolamento da suíte em relação à máquina que a roda.

O RAGX lê DUAS coisas fora do projeto: o hub multiprojeto (`~/.ragx/hub`) e a
configuração do usuário (`~/.config/ragx/config.toml`). Sem isolamento, a
suíte passa a depender do que o desenvolvedor tem instalado — e foi
exatamente isso que aconteceu: `test_list_projects` esperava o projeto `demo`
e recebia o primeiro projeto registrado no hub da máquina. Verde no CI, vermelho
na máquina de quem tinha outros projetos; nenhum dos dois dizia nada sobre o
código.

Um teste que lê o `$HOME` real também ESCREVE nele: `hub sync` registraria
projetos de fixture no hub de verdade da pessoa. Redirecionar aqui, uma vez,
para a sessão inteira, resolve os dois.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def hub_isolado(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Aponta hub e config de usuário para um diretório temporário da sessão.

    `autouse` de propósito: um teste que precisasse LEMBRAR de pedir isolamento
    é um teste que um dia esquece. E o esquecimento só aparece na máquina de
    outra pessoa.
    """
    casa = tmp_path_factory.mktemp("casa")
    (casa / ".ragx" / "hub").mkdir(parents=True, exist_ok=True)

    # Redireciona o HOME e pronto. O hub default (`~/.ragx/hub`) e a config do
    # usuário (`~/.config/ragx/config.toml`) passam por `expanduser`, que
    # respeita HOME no POSIX e USERPROFILE no Windows — então os dois seguem
    # o redirecionamento sozinhos.
    #
    # Deliberadamente NÃO se usa `RAGX_HUB_PATH`: variável de ambiente vence
    # o `ragx.toml`, e isso atropelaria os testes que apontam o hub para um
    # diretório próprio (`tests/integration/test_base.py`). Isolar não pode
    # significar tirar do teste a escolha que ele fez de propósito.
    os.environ["HOME"] = str(casa)
    os.environ["USERPROFILE"] = str(casa)

    # Com HOME redirecionado, `expanduser` só acerta se o cache do pathlib não
    # tiver congelado o valor antigo — conferimos em vez de torcer.
    assert Path(os.path.expanduser("~")).resolve() == casa.resolve(), (
        "o redirecionamento de HOME não pegou; a suíte leria a máquina real"
    )
