"""Código legítimo — DEVE ser indexado."""
import os


class OrderService:
    """Cria e consulta pedidos."""

    def __init__(self, repo):
        self.repo = repo

    def create(self, payload: dict) -> dict:
        """Cria um pedido a partir do payload validado."""
        return self.repo.save(payload)


def get_api_key() -> str:
    return os.environ["API_KEY"]
