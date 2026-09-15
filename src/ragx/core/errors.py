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
