"""Arquivo legítimo com UM achado isolado.

Em `balanced` -> redige o valor e indexa o resto.
Em `strict`   -> o arquivo inteiro é bloqueado.
"""
DEBUG = True
TIMEOUT = 30
RETRIES = 3
INTERNAL_SIGNING_SECRET = "hQ7vN2mK9pL4xR8tW3zA6bY1cD5eF0gJ"


def build_client(base_url: str):
    """Monta o cliente HTTP interno."""
    return {"base_url": base_url, "timeout": TIMEOUT}
