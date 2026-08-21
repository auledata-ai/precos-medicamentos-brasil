"""Cálculo dos números publicáveis, a partir das marts.

Cada função devolve um dicionário e não imprime nada. A separação existe
para os testes poderem verificar a aritmética contra dados sintéticos, que é
onde os erros que produzem números plausíveis se escondem.
"""

from __future__ import annotations

from dataclasses import dataclass

# Acima desta razão face à mediana do grupo, um registro é tratado como cauda
# extrema. Não é um limiar de suspeita: serve para medir a sensibilidade do
# agregado aos valores absurdos, e nada mais.
RAZAO_EXTREMA = 1000
RAZAO_ALTA = 100

# Abaixo deste número de registros a mediana do grupo oscila com um único
# contrato, e a dispersão medida passa a ser o tamanho da amostra.
MINIMO_POR_GRUPO = 30


@dataclass(frozen=True)
class Cobertura:
    registros: int
    compras: int
    fornecedores: int
    municipios: int
    primeiro_dia: str
    ultimo_dia: str


def cobertura(ligacao) -> Cobertura:
    linha = ligacao.execute(
        """
        select count(*)                          as registros,
               count(distinct id_compra)         as compras,
               count(distinct cnpj_fornecedor)   as fornecedores,
               count(distinct codigo_municipio)  as municipios,
               min(data_compra)::text            as primeiro_dia,
               max(data_compra)::text            as ultimo_dia
          from dbt_marts.mart_precos
        """
    ).fetchone()
    return Cobertura(**linha)


def quarentena(ligacao) -> dict:
    """Quanto foi excluído e porquê.

    O total conta registros, não motivos: um registro com dois motivos entra
    uma vez. Somar as linhas do resumo daria um número maior do que a
    realidade, e é esse o erro que esta separação evita.
    """
    total = ligacao.execute(
        "select count(*) as n from dbt_quarentena.quarentena_precos"
    ).fetchone()["n"]
    base = ligacao.execute("select count(*) as n from dbt_marts.mart_precos").fetchone()["n"]
    motivos = ligacao.execute(
        "select motivo, registros, porcentagem_do_total"
        "  from dbt_quarentena.quarentena_resumo order by registros desc"
    ).fetchall()
    return {
        "registros_excluidos": total,
        "registros_analisados": base,
        "porcentagem_excluida": round(100 * total / (total + base), 4),
        # `numeric` chega como Decimal e nao serializa em JSON. A conversao
        # e aqui, junto da consulta, e nao no escritor: quem le o JSON nao
        # tem de saber que a fonte era Postgres.
        "por_motivo": [
            {
                "motivo": m["motivo"],
                "registros": m["registros"],
                "porcentagem_do_total": float(m["porcentagem_do_total"]),
            }
            for m in motivos
        ],
    }


def dispersao_tipica(ligacao) -> dict:
    """Dispersão do miolo do mercado, não dos extremos.

    A razão entre o percentil 75 e o 25 ignora os valores absurdos das
    pontas de propósito: mede o que separa uma compra cara de uma barata
    entre compras normais do mesmo produto, tamanho e ano.
    """
    linha = ligacao.execute(
        """
        with razoes as (
            select p75 / p25 as razao
              from dbt_marts.mart_dispersao_grupo
             where amostra_suficiente and p25 > 0
        )
        select count(*)                                                as grupos,
               percentile_disc(0.25) within group (order by razao)     as q1,
               percentile_disc(0.50) within group (order by razao)     as mediana,
               percentile_disc(0.75) within group (order by razao)     as q3,
               percentile_disc(0.90) within group (order by razao)     as p90
          from razoes
        """
    ).fetchone()
    return {k: (float(v) if k != "grupos" else v) for k, v in linha.items()}


def cauda_extrema(ligacao) -> dict:
    """Caracterização da cauda, e o padrão de registro que a explica.

    `quantidade = 1` é raro na base e domina os registros mais absurdos. É a
    assinatura de um lote inteiro lançado como uma única unidade: a
    Sinvastatina a R$ 750.000 não é um comprimido caro, é uma compra inteira
    registrada como se fosse um.
    """
    faixas = ligacao.execute(
        f"""
        select case when razao_mediana >= {RAZAO_EXTREMA} then 'extrema'
                    when razao_mediana >= {RAZAO_ALTA}    then 'alta'
                    else 'moderada' end                        as faixa,
               count(*)                                        as registros,
               count(*) filter (where quantidade = 1)          as com_quantidade_um
          from dbt_marts.mart_compras_atipicas
         group by 1
        """  # noqa: S608 -- limiares são constantes do módulo
    ).fetchall()
    base = ligacao.execute(
        """
        select round(100.0 * count(*) filter (where quantidade = 1)
                     / nullif(count(*), 0), 4) as pct
          from dbt_marts.mart_precos
        """
    ).fetchone()["pct"]

    por_faixa = {}
    for f in faixas:
        pct = round(100 * f["com_quantidade_um"] / f["registros"], 1)
        por_faixa[f["faixa"]] = {
            "registros": f["registros"],
            "com_quantidade_um": f["com_quantidade_um"],
            "porcentagem_com_quantidade_um": pct,
        }
    return {
        "por_faixa": por_faixa,
        "porcentagem_com_quantidade_um_na_base": float(base),
    }


def agregado(ligacao) -> dict:
    """Gasto total e quanto dele ficou acima da mediana do próprio grupo.

    `diferenca_para_a_mediana` é o nome certo e `prejuízo` seria o errado.
    Pagar acima da mediana tem explicações legítimas: urgência, quantidade
    mínima, logística para município remoto. O que o número mede é a
    distância a uma referência interna, não uma perda apurada.

    Os três cenários existem para responder à objeção óbvia: o total está a
    ser puxado pelos absurdos? A resposta tem de vir do próprio cálculo.
    """
    linhas = ligacao.execute(
        f"""
        with base as (
            select p.preco_unitario, p.quantidade, d.mediana,
                   p.preco_unitario / d.mediana as razao
              from dbt_marts.mart_precos p
              join dbt_marts.mart_dispersao_grupo d
                on p.grupo_comparavel = d.grupo_comparavel
               and extract(year from p.data_compra)::int = d.ano
             where d.amostra_suficiente and d.mediana > 0
        ),
        cenarios as (
            select 'todos' as cenario, * from base
            union all
            select 'sem_extremos', * from base where razao < {RAZAO_EXTREMA}
            union all
            select 'sem_altos', * from base where razao < {RAZAO_ALTA}
        )
        select cenario,
               count(*)                                                as registros,
               sum(preco_unitario * quantidade)                        as gasto,
               sum(greatest(preco_unitario - mediana, 0) * quantidade) as acima_da_mediana
          from cenarios group by cenario
        """  # noqa: S608 -- limiares são constantes do módulo
    ).fetchall()

    resultado = {}
    for linha in linhas:
        gasto = float(linha["gasto"])
        acima = float(linha["acima_da_mediana"])
        resultado[linha["cenario"]] = {
            "registros": linha["registros"],
            "gasto": round(gasto, 2),
            "acima_da_mediana": round(acima, 2),
            "porcentagem_acima": round(100 * acima / gasto, 2) if gasto else None,
        }
    return resultado


def tudo(ligacao) -> dict:
    return {
        "cobertura": vars(cobertura(ligacao)),
        "quarentena": quarentena(ligacao),
        "dispersao_tipica": dispersao_tipica(ligacao),
        "cauda_extrema": cauda_extrema(ligacao),
        "agregado": agregado(ligacao),
    }
