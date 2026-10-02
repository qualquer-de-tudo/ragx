from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ragx.indexing import lock


def test_segunda_tentativa_falha_enquanto_a_primeira_segura(tmp_path: Path) -> None:
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    assert lock.try_acquire(tmp_path, "index", "hook:post-commit") is False
    h = lock.holder(tmp_path)
    assert h is not None and h["pid"] == os.getpid() and h["source"] == "cli"
    lock.release(tmp_path)
    assert lock.holder(tmp_path) is None
    assert lock.try_acquire(tmp_path, "index", "panel") is True
    lock.release(tmp_path)


def test_trava_de_processo_morto_e_assumida(tmp_path: Path) -> None:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    (tmp_path / lock.LOCK_NAME).write_text(
        json.dumps({"pid": p.pid, "op": "index", "source": "cli", "started_at": "x"}),
        encoding="utf-8",
    )
    assert lock.pid_alive(p.pid) is False
    assert lock.try_acquire(tmp_path, "index", "panel") is True
    assert lock.holder(tmp_path)["pid"] == os.getpid()
    lock.release(tmp_path)


def test_trava_ilegivel_e_assumida(tmp_path: Path) -> None:
    (tmp_path / lock.LOCK_NAME).write_text("lixo", encoding="utf-8")
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    lock.release(tmp_path)


def test_pid_do_proprio_processo_esta_vivo() -> None:
    assert lock.pid_alive(os.getpid()) is True


def test_pendencia_guarda_a_ultima_origem_e_e_consumida(tmp_path: Path) -> None:
    assert lock.take_pending(tmp_path) is None
    lock.mark_pending(tmp_path, "hook:post-commit")
    lock.mark_pending(tmp_path, "hook:post-checkout")
    assert lock.is_pending(tmp_path) is True
    assert lock.take_pending(tmp_path) == "hook:post-checkout"
    assert lock.is_pending(tmp_path) is False


def test_trava_publicada_nunca_fica_vazia(tmp_path: Path) -> None:
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    raw = (tmp_path / lock.LOCK_NAME).read_text(encoding="utf-8")
    assert raw  # publicação por link físico: nunca vazio no caminho final
    data = json.loads(raw)
    assert data["pid"] == os.getpid()
    assert data["source"] == "cli"
    lock.release(tmp_path)


def test_takeover_com_visao_desatualizada_nao_derruba_trava_viva(tmp_path: Path) -> None:
    """B ainda acredita que o dono é o pid morto original (visão obsoleta).

    A já assumiu a trava morta pelo caminho público (try_acquire). B tenta
    assumir a mesma trava morta diretamente pelo helper interno, usando um
    payload próprio — simula duas leituras concorrentes do mesmo holder
    morto que chegam a conclusões diferentes sobre o estado atual.
    """
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    dead_pid = p.pid
    (tmp_path / lock.LOCK_NAME).write_text(
        json.dumps({"pid": dead_pid, "op": "index", "source": "cli", "started_at": "x"}),
        encoding="utf-8",
    )

    assert lock.try_acquire(tmp_path, "index", "A") is True
    a_holder = lock.holder(tmp_path)
    assert a_holder is not None and a_holder["pid"] == os.getpid()

    payload_b = json.dumps(
        {"pid": 4_000_000, "op": "index", "source": "B", "started_at": "y"}
    )
    assert lock._take_over(tmp_path, dead_pid, payload_b) is False

    # A trava de A sobrevive intacta; B não conseguiu assumir.
    assert lock.holder(tmp_path) == a_holder
    lock.release(tmp_path)


def test_release_nao_mexe_em_trava_alheia(tmp_path: Path) -> None:
    foreign = {"pid": os.getpid() + 1, "op": "index", "source": "watch", "started_at": "x"}
    (tmp_path / lock.LOCK_NAME).write_text(json.dumps(foreign), encoding="utf-8")
    lock.release(tmp_path)
    assert lock.holder(tmp_path) == foreign


def test_publica_com_fallback_quando_link_fisico_nao_e_suportado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAT32/exFAT/alguns compartilhamentos SMB não suportam link físico.

    `os.link` levanta `OSError` genérico (não `FileExistsError`) nesses
    sistemas de arquivos; `_publish` precisa cair para `O_EXCL` direto, sem
    deixar a trava impossível de adquirir.
    """

    def sem_link(src: object, dst: object) -> None:
        raise OSError(errno.EPERM, "operação não suportada")

    monkeypatch.setattr(os, "link", sem_link)
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    h = lock.holder(tmp_path)
    assert h is not None and h["pid"] == os.getpid() and h["source"] == "cli"
    lock.release(tmp_path)


def test_takeover_trata_erro_de_so_no_rename_como_ocupado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WinError 32: outro processo tem a trava aberta para leitura.

    Confirmado neste host Windows — `os.rename` levanta `PermissionError`
    (uma `OSError`) em vez de completar ou de dar `FileNotFoundError`.
    `_take_over` não pode deixar isso escapar para `try_acquire`; precisa
    tratar como "ocupado" e devolver `False`, mantendo a trava original
    intacta.
    """
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    dead_pid = p.pid
    original = json.dumps(
        {"pid": dead_pid, "op": "index", "source": "cli", "started_at": "x"}
    )
    (tmp_path / lock.LOCK_NAME).write_text(original, encoding="utf-8")

    def deny(src: object, dst: object) -> None:
        raise PermissionError(13, "acesso negado")

    monkeypatch.setattr(os, "rename", deny)
    assert lock.try_acquire(tmp_path, "index", "outro") is False
    assert (tmp_path / lock.LOCK_NAME).read_text(encoding="utf-8") == original


# ── PID reutilizado (RAGX-0153) ─────────────────────────────────────────
def _stat_com_starttime(nome: str, starttime: str) -> str:
    """Linha de `/proc/<pid>/stat`: pid (nome) estado ppid ... campo 22 = starttime ... até o campo 52."""
    campos = [str(i) for i in range(4, 53)]  # campos 4..52
    campos[22 - 4] = starttime
    return f"1234 ({nome}) S " + " ".join(campos) + "\n"


def test_starttime_do_stat_conta_os_campos_depois_do_ultimo_parenteses() -> None:
    assert lock._starttime_do_stat(_stat_com_starttime("python", "987654")) == "987654"
    # o nome do processo pode ter espaço e `)`: só o ÚLTIMO `)` separa o nome dos campos
    assert lock._starttime_do_stat(_stat_com_starttime("meu (proc) com espaco", "42")) == "42"
    assert lock._starttime_do_stat(_stat_com_starttime("a)b", "7")) == "7"
    assert lock._starttime_do_stat("sem parenteses") is None
    assert lock._starttime_do_stat("1 (curto) S 1 2 3") is None


def test_proc_token_do_proprio_processo_e_estavel_e_pid_invalido_nao_tem() -> None:
    primeiro = lock.proc_token(os.getpid())
    assert primeiro is not None and primeiro == lock.proc_token(os.getpid())
    assert lock.proc_token(0) is None and lock.proc_token(-5) is None


def test_proc_token_distingue_processos_e_nao_muda_quando_o_filho_acaba() -> None:
    filho = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        do_filho = lock.proc_token(filho.pid)
        assert do_filho is not None and do_filho != lock.proc_token(os.getpid())
    finally:
        filho.kill()
        filho.wait()
    # depois de encerrado: ou não dá mais para ler, ou continua sendo a MESMA identidade (nunca outra)
    assert lock.proc_token(filho.pid) in (None, do_filho)


@pytest.mark.skipif(sys.platform != "win32", reason="GetProcessTimes é do Windows")
def test_proc_token_no_windows_e_o_instante_de_criacao_do_processo() -> None:
    token = lock.proc_token(os.getpid())
    assert token is not None and token.isdigit() and int(token) > 0


def test_try_acquire_grava_o_proc_do_dono(tmp_path: Path) -> None:
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    h = lock.holder(tmp_path)
    assert h is not None and h["proc"] == lock.proc_token(os.getpid())
    lock.release(tmp_path)


def _trava_com(tmp_path: Path, **extra: object) -> None:
    (tmp_path / lock.LOCK_NAME).write_text(
        json.dumps({"pid": os.getpid(), "op": "index", "source": "cli", "started_at": "x", **extra}),
        encoding="utf-8",
    )


def test_pid_vivo_com_token_trocado_e_pid_reutilizado_e_a_trava_e_assumida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O número existe (é de OUTRO processo, hoje), mas o processo que gravou a trava já morreu."""
    _trava_com(tmp_path, proc="token-do-indexador-que-morreu")
    atual = lock.proc_token(os.getpid())
    assert atual != "token-do-indexador-que-morreu"
    assert lock.holder_alive(lock.holder(tmp_path)) is False
    assert lock.try_acquire(tmp_path, "index", "panel") is True
    assert lock.holder(tmp_path)["source"] == "panel" and lock.holder(tmp_path)["proc"] == atual
    lock.release(tmp_path)


def test_pid_vivo_com_o_mesmo_token_continua_bloqueando(tmp_path: Path) -> None:
    _trava_com(tmp_path, proc=lock.proc_token(os.getpid()))
    assert lock.holder_alive(lock.holder(tmp_path)) is True
    assert lock.try_acquire(tmp_path, "index", "panel") is False


def test_trava_antiga_sem_proc_e_pid_vivo_continua_bloqueando(tmp_path: Path) -> None:
    """Compatibilidade: a trava de uma versão anterior não tem `proc`; vale só o número, como sempre."""
    _trava_com(tmp_path)
    assert lock.holder_alive(lock.holder(tmp_path)) is True
    assert lock.try_acquire(tmp_path, "index", "panel") is False
    _trava_com(tmp_path, proc=None)  # quem não conseguiu ler o próprio token grava `null`
    assert lock.try_acquire(tmp_path, "index", "panel") is False


def test_token_atual_ilegivel_nao_arrisca_assumir_a_trava_de_um_dono_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trava_com(tmp_path, proc="qualquer")
    monkeypatch.setattr(lock, "proc_token", lambda pid: None)  # ex.: ERROR_ACCESS_DENIED em processo de outro usuário
    assert lock.holder_alive(lock.holder(tmp_path)) is True
    assert lock.try_acquire(tmp_path, "index", "panel") is False


def test_holder_alive_respeita_o_monkeypatch_de_pid_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Os testes de integração trocam `lock.pid_alive`; `holder_alive` o resolve pelo módulo, na hora."""
    _trava_com(tmp_path, proc=lock.proc_token(os.getpid()))
    monkeypatch.setattr(lock, "pid_alive", lambda pid: False)
    assert lock.holder_alive(lock.holder(tmp_path)) is False
    assert lock.holder_alive(None) is False and lock.holder_alive({"pid": "x"}) is False
