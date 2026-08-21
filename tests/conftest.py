"""Fixtures partilhadas. Os payloads são capturas reais da API, não invenções."""

import json
import os
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


@pytest.fixture
def conexao():
    """Ligação ao Postgres do compose, dentro de uma transação revertida.

    Cada teste vê uma base limpa sem precisar de a recriar, e nenhum deixa
    resíduo para o seguinte.
    """
    psycopg = pytest.importorskip("psycopg")
    from ingestao.repositorio import criar_esquema

    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN não definido")
    try:
        ligacao = psycopg.connect(dsn, row_factory=psycopg.rows.dict_row)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres indisponível: {exc}")
    with ligacao:
        criar_esquema(ligacao)
        ligacao.commit()
        ligacao.execute("truncate raw.catalogo, raw.precos, raw.controlo_ingestao")
        yield ligacao
        ligacao.rollback()
    ligacao.close()
