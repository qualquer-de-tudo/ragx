"""Erros do RAGX. Cada um mapeia para um exit code documentado (docs/14-cli.md)."""

from __future__ import annotations


class RagxError(Exception):
    exit_code = 1


class UsageError(RagxError):
    """Argumento ou configuração inválida."""

    exit_code = 2


class EnvError(RagxError):
    """Banco corrompido, FTS5 ausente, embedder indisponível."""

    exit_code = 3


class SecurityBlockedError(RagxError):
    """Achado bloqueante. Nunca carrega o valor do segredo."""

    exit_code = 1


class BudgetExceededError(RagxError):
    """Orçamento de tamanho estourado — recusa de escrita, nunca truncamento."""

    exit_code = 1


class ParseError(RagxError):
    """Falha de parsing: degrada para fallback, não derruba a indexação."""


class IndexBusyError(RagxError):
    """Outra indexação segura a trava; o pedido ficou agendado."""

    exit_code = 4

    def __init__(self, holder: dict[str, object] | None):
        self.holder = holder or {}
        who = self.holder.get("source", "outra origem")
        pid = self.holder.get("pid", "?")
        super().__init__(
            f"outra indexação está rodando (origem {who}, pid {pid}). "
            "Este pedido ficou agendado e roda quando ela terminar."
        )
