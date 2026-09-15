"""Entropia de Shannon — o sinal de recall do scanner de conteúdo."""

from __future__ import annotations

import math
from collections import Counter


def shannon(value: str) -> float:
    """Bits por caractere. Texto natural fica ~2-3; chave aleatória, >4."""
    if not value:
        return 0.0
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in Counter(value).values())


def looks_random(value: str, min_entropy: float = 3.0, min_length: int = 12) -> bool:
    """Entropia sozinha gera falso positivo demais; estes cortes reduzem o ruído."""
    if len(value) < min_length:
        return False
    if len(set(value)) < 6:  # 'aaaaaaaaaaaa' tem entropia 0
        return False
    # Frase em texto natural: várias palavras separadas por espaço.
    if value.count(" ") >= 2:
        return False
    return shannon(value) >= min_entropy
