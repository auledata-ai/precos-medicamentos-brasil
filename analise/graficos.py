"""Conjuntos de dados dos gráficos, calculados a partir das marts.

Os gráficos leem deste JSON. Nenhum valor é digitado no HTML: um número
copiado à mão numa peça visual é um número que ninguém volta a conferir.
"""

from __future__ import annotations

from analise.resultados import RAZAO_ALTA, RAZAO_EXTREMA

# Largura da barra do histograma, em múltiplos da razão. Um quarto separa
# o miolo da distribuição sem transformar a cauda numa serra.
PASSO_HISTOGRAMA = 0.25
RAZAO_MAXIMA_HISTOGRAMA = 4.0


def histograma_dispersao(ligacao) -> dict:
    """Distribuição da razão entre o percentil 75 e o 25, por grupo.

    Tudo acima de 4x cai numa barra final em vez de esticar o eixo. Esticar
    daria dez barras invisíveis e uma legível, e a forma da distribuição é
    exatamente o que este gráfico existe para mostrar.
    """
    linhas = ligacao.execute(
        """
        with razoes as (
            select least(p75 / p25, %(teto)s) as razao
              from dbt_marts.mart_dispersao_grupo
             where amostra_suficiente and p25 > 0
        )
        select floor(razao / %(passo)s) * %(passo)s as inicio, count(*) as grupos
          from razoes group by 1 order by 1
        """,
        {"passo": PASSO_HISTOGRAMA, "teto": RAZAO_MAXIMA_HISTOGRAMA},
    ).fetchall()

    barras = []
    for linha in linhas:
        inicio = float(linha["inicio"])
        no_teto = inicio >= RAZAO_MAXIMA_HISTOGRAMA
        barras.append(
            {
                "inicio": inicio,
                "fim": None if no_teto else round(inicio + PASSO_HISTOGRAMA, 2),
                "rotulo": f"{RAZAO_MAXIMA_HISTOGRAMA:.1f}x ou mais".replace(".", ",")
                if no_teto
                else f"{inicio:.2f}".replace(".", ","),
                "grupos": linha["grupos"],
            }
        )
    total = sum(b["grupos"] for b in barras)
    ate_175 = sum(b["grupos"] for b in barras if b["inicio"] < 1.75)
    return {
        "barras": barras,
        "total_grupos": total,
        "grupos_ate_1_75": ate_175,
        "porcentagem_ate_1_75": round(100 * ate_175 / total, 1),
    }


def assinatura_quantidade_um(ligacao) -> dict:
    """Porcentagem de registros com quantidade 1, por faixa de exagero.

    A linha de referência é a taxa na base inteira. Sem ela, três barras
    altas não dizem nada: o que prova o padrão é a distância à base.
    """
    faixas = ligacao.execute(
        f"""
        select case when razao_mediana >= {RAZAO_EXTREMA} then 'extrema'
                    when razao_mediana >= {RAZAO_ALTA}    then 'alta'
                    else 'moderada' end               as faixa,
               count(*)                               as registros,
               count(*) filter (where quantidade = 1) as com_quantidade_um
          from dbt_marts.mart_compras_atipicas group by 1
        """  # noqa: S608 -- limiares são constantes do módulo
    ).fetchall()
    base = float(
        ligacao.execute(
            """
            select 100.0 * count(*) filter (where quantidade = 1)
                   / nullif(count(*), 0) as pct from dbt_marts.mart_precos
            """
        ).fetchone()["pct"]
    )

    rotulos = {
        "extrema": f"{RAZAO_EXTREMA:,}x ou mais".replace(",", "."),
        "alta": f"{RAZAO_ALTA}x a {RAZAO_EXTREMA:,}x".replace(",", "."),
        "moderada": f"10x a {RAZAO_ALTA}x",
    }
    ordem = ["extrema", "alta", "moderada"]
    por_faixa = {f["faixa"]: f for f in faixas}
    barras = [
        {
            "faixa": rotulos[chave],
            "registros": por_faixa[chave]["registros"],
            "porcentagem": round(
                100 * por_faixa[chave]["com_quantidade_um"] / por_faixa[chave]["registros"],
                1,
            ),
        }
        for chave in ordem
        if chave in por_faixa
    ]
    return {
        "barras": barras,
        "base": round(base, 2),
        "concentracao": round(barras[0]["porcentagem"] / base, 0) if base else None,
    }


def tudo(ligacao) -> dict:
    return {
        "histograma_dispersao": histograma_dispersao(ligacao),
        "assinatura_quantidade_um": assinatura_quantidade_um(ligacao),
    }
