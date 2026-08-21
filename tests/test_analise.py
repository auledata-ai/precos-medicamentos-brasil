"""Verificação da aritmética que vai a público.

Os números aqui são pequenos de propósito, para poderem ser conferidos de
cabeça. Testar a análise contra a base real só provaria que ela devolve o
que devolveu da última vez.
"""

import pytest
from analise import resultados


def _dsn_de_testes() -> str | None:
    from tests.conftest import BASE_DE_TESTES, _dsn_do_ambiente

    dsn = _dsn_do_ambiente()
    if not dsn:
        return None
    import re

    return re.sub(r"/[^/?]+(\?|$)", f"/{BASE_DE_TESTES}\\1", dsn)


@pytest.fixture
def marts():
    """Marts sintéticas na base de testes, com forma igual à das reais.

    Um grupo, quatro compras: três a 10 e uma a 100. A mediana é 10, e a
    compra de 100 está 90 acima dela. Todos os resultados esperados abaixo
    saem desta linha.
    """
    psycopg = pytest.importorskip("psycopg")
    dsn = _dsn_de_testes()
    if not dsn:
        pytest.skip("sem credenciais de Postgres no ambiente")
    try:
        ligacao = psycopg.connect(dsn, row_factory=psycopg.rows.dict_row)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")

    ligacao.execute("drop schema if exists dbt_marts cascade")
    ligacao.execute("drop schema if exists dbt_quarentena cascade")
    ligacao.execute("create schema dbt_marts")
    ligacao.execute("create schema dbt_quarentena")
    ligacao.execute("""
        create table dbt_marts.mart_precos (
            id_compra text, id_item_compra text, cnpj_fornecedor text,
            codigo_municipio text, data_compra date, grupo_comparavel text,
            preco_unitario numeric, quantidade numeric
        )""")
    ligacao.execute("""
        insert into dbt_marts.mart_precos values
            ('c1','i1','F1','M1','2025-03-01','G',  10, 1),
            ('c1','i2','F1','M1','2025-03-01','G',  10, 1),
            ('c2','i1','F2','M2','2025-04-01','G',  10, 1),
            ('c3','i1','F2','M2','2025-05-01','G', 100, 1)
        """)
    ligacao.execute("""
        create table dbt_marts.mart_dispersao_grupo (
            grupo_comparavel text, ano int, n_registos int,
            p25 numeric, mediana numeric, p75 numeric, amostra_suficiente boolean
        )""")
    ligacao.execute("""
        insert into dbt_marts.mart_dispersao_grupo values
            ('G', 2025, 30, 10, 10, 20, true),
            -- Grupo sem amostra: tem de ficar fora de tudo.
            ('H', 2025,  5,  1,  1, 99, false)
        """)
    ligacao.execute("""
        create table dbt_marts.mart_compras_atipicas (
            razao_mediana numeric, quantidade numeric
        )""")
    ligacao.execute("""
        insert into dbt_marts.mart_compras_atipicas values
            (5000, 1), (5000, 1), (5000, 7),
            (500, 1), (500, 3),
            (50, 4)
        """)
    ligacao.execute("""
        create table dbt_quarentena.quarentena_precos (
            id_compra text, motivos text[], n_motivos int
        )""")
    ligacao.execute("""
        insert into dbt_quarentena.quarentena_precos values ('q1','{a}',1)
        """)
    ligacao.execute("""
        create table dbt_quarentena.quarentena_resumo (
            motivo text, registos int, percentagem_do_total numeric
        )""")
    ligacao.execute("insert into dbt_quarentena.quarentena_resumo values ('a',1,20.0)")
    ligacao.commit()
    try:
        yield ligacao
    finally:
        ligacao.close()


def test_cobertura_conta_entidades_distintas_e_nao_linhas(marts):
    c = resultados.cobertura(marts)
    assert c.registos == 4
    assert c.compras == 3  # c1 aparece em duas linhas e conta uma vez
    assert c.fornecedores == 2
    assert c.municipios == 2
    assert c.primeiro_dia == "2025-03-01"
    assert c.ultimo_dia == "2025-05-01"


def test_percentagem_excluida_usa_o_total_antes_da_exclusao(marts):
    q = resultados.quarentena(marts)
    assert q["registos_excluidos"] == 1
    assert q["registos_analisados"] == 4
    # 1 de 5, e nao 1 de 4: o denominador tem de incluir o que foi excluido.
    assert q["percentagem_excluida"] == pytest.approx(20.0)


def test_dispersao_ignora_grupos_sem_amostra(marts):
    d = resultados.dispersao_tipica(marts)
    assert d["grupos"] == 1  # o grupo H tem 99/1 e ficaria em primeiro
    assert d["mediana"] == pytest.approx(2.0)  # 20 / 10


def test_cauda_extrema_separa_faixas_e_mede_quantidade_um(marts):
    c = resultados.cauda_extrema(marts)
    assert c["por_faixa"]["extrema"]["registos"] == 3
    assert c["por_faixa"]["extrema"]["percentagem_com_quantidade_um"] == pytest.approx(66.7)
    assert c["por_faixa"]["alta"]["registos"] == 2
    assert c["por_faixa"]["moderada"]["registos"] == 1
    assert c["percentagem_com_quantidade_um_na_base"] == pytest.approx(100.0)


def test_agregado_soma_apenas_o_que_esta_acima_da_mediana(marts):
    a = resultados.agregado(marts)["todos"]
    assert a["registos"] == 4
    assert a["gasto"] == pytest.approx(130.0)
    # Só a compra de 100 está acima: 90. As de 10 estão na mediana e as
    # abaixo nunca compensam as acima, por isso o `greatest(..., 0)`.
    assert a["acima_da_mediana"] == pytest.approx(90.0)
    assert a["percentagem_acima"] == pytest.approx(69.23)


def test_agregado_exclui_extremos_no_cenario_correspondente(marts):
    a = resultados.agregado(marts)
    # 100 / 10 = 10x, abaixo dos limiares: nenhum cenario a remove.
    assert a["sem_extremos"]["registos"] == 4
    assert a["sem_altos"]["registos"] == 4
