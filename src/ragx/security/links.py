"""Symlink ou junction: o que o walker não segue para fora da raiz (ameaça A8).

No Windows, uma junction (`mklink /J`, o que o pnpm cria, e que não exige
privilégio) NÃO é symlink para o Python: `Path.is_symlink()` devolve falso e o
walker descia nela, indexando uma pasta de fora do projeto. Este módulo é só
stdlib, para que `walk.py` e `ignore_engine.py` o usem sem ciclo.

Só `IO_REPARSE_TAG_MOUNT_POINT` conta. Outros reparse points (OneDrive com
arquivos sob demanda, `AppExecLink`) NÃO são junctions e continuam sendo
percorridos normalmente.
"""

from __future__ import annotations

import os
import stat
import sys

# Valor fixo do Windows (`winnt.h`): evita depender de `stat` expor a constante.
_MOUNT_POINT = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def is_junction(path: str | os.PathLike[str]) -> bool:
    """Junction do Windows. Sempre falso fora do Windows, sem syscall."""
    if sys.platform != "win32":
        return False
    try:
        return getattr(os.lstat(path), "st_reparse_tag", 0) == _MOUNT_POINT
    except OSError:
        return False


def is_link(path: str | os.PathLike[str] | os.DirEntry[str]) -> bool:
    """Symlink OU junction. Caminho inexistente ou ilegível devolve falso."""
    p = path.path if isinstance(path, os.DirEntry) else path
    try:
        if os.path.islink(p):
            return True
    except OSError:
        return False
    return is_junction(p)
