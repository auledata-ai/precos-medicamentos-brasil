"""Fixtures partilhadas. Os payloads são capturas reais da API, não invenções."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def carregar(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text())


@pytest.fixture
def catalogo_real() -> dict:
    return carregar("catalogo_pagina.json")


@pytest.fixture
def precos_reais() -> dict:
    """Cimetidina 400 MG: duas unidades de fornecimento e preços de R$ 0,20 a
    R$ 266,00 pelo mesmo comprimido. É o caso difícil de propósito."""
    return carregar("precos_cimetidina.json")
