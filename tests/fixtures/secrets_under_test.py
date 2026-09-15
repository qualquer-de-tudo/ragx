"""Lista única de segredos plantados na fixture.

TODOS SÃO FALSOS. Têm formato válido de propósito, para acionar as regras.
É esta lista que os testes usam para varrer todas as superfícies.

O pre-commit do RAGX tem exceção explícita para tests/fixtures/ — comentada em
docs/13-testes-hardening.md. Sem essa exceção, o próprio projeto não commitaria
sua fixture de teste.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "secret_project"

SECRETS_UNDER_TEST: list[str] = [
    "AKIAIOSFODNN7EXAMPLE",
    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "Tr0ub4dor&3xKcd9Zq",
    "sk_live_51H8xQ2KZvLmNpQrStUvWxYz0123456789",
    "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
    "MIIEowIBAAKCAQEAxK7LmQnVfPqRsT8uWvXyZ0123456789abcdefGHIJKLMNOPQR",
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDQ8pLmNvBxKzTr",
    "pG7x2Qm9ZvLk4Rt8",
    "AIzaSyD3mOk3yF4kEaPiK3yV4lU3xYzAbCdEfGh",
    "hQ7vN2mK9pL4xR8tW3zA6bY1cD5eF0gJ",
]

# Arquivos que DEVEM ser bloqueados.
MUST_BLOCK: list[str] = [
    ".env",
    ".env.production",
    "credentials.json",
    "id_rsa",
    "private.pem",
    "config.yaml",
    "docker-compose.yml",
]

# Arquivos que DEVEM ser indexados. Um gate que bloqueia tudo passaria na
# varredura de segredos e seria inútil — este é o teste que impede isso.
MUST_INDEX: list[str] = [
    ".env.example",
    "src/app.py",
    "docs/setup.md",
    "tests/fixtures/sample.json",
]

# Arquivo legítimo com um achado isolado: redige, não bloqueia.
MUST_REDACT: list[str] = ["src/settings.py"]


def leaked(haystack: str) -> list[str]:
    """Quais segredos aparecem no texto dado. Vazio é o único resultado aceitável."""
    return [s for s in SECRETS_UNDER_TEST if s in haystack]
