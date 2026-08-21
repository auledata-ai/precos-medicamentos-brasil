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
    """Ligação a uma base de dados só de testes, recriada a cada teste.

    Não serve reverter a transação no fim: o código sob teste faz `commit`
    por item, de propósito, e o rollback não desfaz o que já foi confirmado.
    Descobrimos isso ao ver dados de teste na base de trabalho.

    Por isso: base separada, recriada do zero. Correr a suite nunca toca nos
    dados reais.
    """
    psycopg = pytest.importorskip("psycopg")
    from ingestao.repositorio import criar_esquema

    dsn = _dsn_do_ambiente()
    if not dsn:
        pytest.skip("sem credenciais de Postgres no ambiente")

    dsn_testes = _garantir_base_de_testes(psycopg, dsn)
    if dsn_testes is None:
        pytest.skip("Postgres indisponível")

    ligacao = psycopg.connect(dsn_testes, row_factory=psycopg.rows.dict_row)
    _recriar(ligacao, criar_esquema)
    try:
        yield ligacao
    finally:
        ligacao.close()


BASE_DE_TESTES = "precos_teste"


def _dsn_do_ambiente() -> str | None:
    """DSN da base de trabalho, do ambiente.

    Aceita `POSTGRES_DSN` inteiro, mas também o monta a partir das variáveis
    soltas do `.env`. Sem isto, um `pytest` sem o script de infra saltava 26
    testes e passava a verde sem ter tocado na base: um resultado verde que
    não prova nada é pior do que um vermelho.
    """
    if dsn := os.environ.get("POSTGRES_DSN"):
        return dsn
    utilizador = os.environ.get("POSTGRES_USER")
    senha = os.environ.get("POSTGRES_PASSWORD")
    base = os.environ.get("POSTGRES_DB")
    if not (utilizador and senha and base):
        return None
    servidor = os.environ.get("POSTGRES_HOST", "localhost")
    porta = os.environ.get("POSTGRES_PORT", "5433")
    return f"postgresql://{utilizador}:{senha}@{servidor}:{porta}/{base}"


def _recriar(ligacao, criar_esquema) -> None:
    """Deita o esquema abaixo e reconstrói.

    Um `truncate` limparia os dados mas manteria a forma antiga das tabelas,
    e um `create table if not exists` não altera o que já existe. Depois de
    mudarmos a chave do controlo de item para PDM, a suite inteira falhou
    contra um esquema obsoleto. Recriar é barato e não deixa essa dúvida.
    """
    ligacao.execute("drop schema if exists raw cascade")
    ligacao.commit()
    criar_esquema(ligacao)
    ligacao.commit()


def _garantir_base_de_testes(psycopg, dsn: str) -> str | None:
    """Cria a base de testes se faltar. Devolve o DSN dela, ou None."""
    import re

    dsn_testes = re.sub(r"/[^/?]+(\?|$)", f"/{BASE_DE_TESTES}\\1", dsn)
    try:
        with psycopg.connect(dsn, autocommit=True) as admin:
            existe = admin.execute(
                "select 1 from pg_database where datname = %s", (BASE_DE_TESTES,)
            ).fetchone()
            if not existe:
                admin.execute(f'create database "{BASE_DE_TESTES}"')
    except psycopg.OperationalError:
        return None
    return dsn_testes
