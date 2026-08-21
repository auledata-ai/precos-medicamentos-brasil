"""Orquestração da coleta: percorre itens, isola falhas, actualiza o controlo.

Esta camada existe para a DAG poder ser fina. Tudo o que aqui está é
testável sem Airflow, com um cliente falso e uma transação revertida.

A regra que domina o desenho: **a falha de um item não pode derrubar o
lote**. São milhares de chamadas contra um portal público; alguma vai
falhar sempre. Um erro não tratado por item significaria perder o trabalho
dos itens já processados nesse lote.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import psycopg

from ingestao.cliente import Cliente, ErroDaFonte, FonteIndisponivel
from ingestao.coleta import coletar_catalogo, coletar_precos_por_pdm
from ingestao.repositorio import (
    VALIDADE_PADRAO,
    guardar_catalogo,
    guardar_precos,
    marcar_coletado,
    marcar_falha,
    pdms_pendentes,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoDoLote:
    """O que aconteceu num lote. Vai para o log da task e para o relatório."""

    pdms: int
    sucesso: int
    sem_compras: int
    falha: int
    registos: int


def sincronizar_catalogo(cliente: Cliente, conexao: psycopg.Connection) -> int:
    """Actualiza o catálogo e cria as linhas de controlo em falta."""
    registos = coletar_catalogo(cliente)
    guardados = guardar_catalogo(conexao, registos)
    conexao.commit()
    logger.info("catálogo sincronizado: %d itens", guardados)
    return guardados


def planear_lotes(
    conexao: psycopg.Connection,
    n_lotes: int,
    validade: timedelta = VALIDADE_PADRAO,
    limite: int | None = None,
    forcar: bool = False,
) -> list[list[str]]:
    """Divide os PDMs pendentes em lotes de tamanho equilibrado.

    Distribui em rodízio e não em blocos contíguos: o catálogo está ordenado
    por código, e códigos próximos tendem a ter volumes de compra parecidos.
    Em blocos, um lote apanharia todos os pesados e seria o único a demorar.
    """
    if n_lotes < 1:
        raise ValueError("n_lotes deve ser pelo menos 1")
    pendentes = pdms_pendentes(conexao, validade=validade, limite=limite, forcar=forcar)
    lotes: list[list[str]] = [[] for _ in range(n_lotes)]
    for posicao, codigo in enumerate(pendentes):
        lotes[posicao % n_lotes].append(codigo)
    return [lote for lote in lotes if lote]


def coletar_lote(
    cliente: Cliente, conexao: psycopg.Connection, codigos: list[str]
) -> ResultadoDoLote:
    """Coleta os preços de cada PDM do lote, com commit por PDM.

    O commit por unidade é deliberado. Se fosse um commit no fim, uma falha a
    meio perderia todo o progresso do lote, que é exactamente o problema que
    a tabela de controlo existe para evitar.
    """
    sucesso = sem_compras = falha = registos = 0

    for codigo in codigos:
        try:
            brutos = coletar_precos_por_pdm(cliente, codigo)
        except (ErroDaFonte, FonteIndisponivel) as exc:
            # Falha esperada da fonte: regista e continua. Rebentar aqui
            # desperdicaria os itens ja processados neste lote.
            marcar_falha(conexao, codigo, str(exc))
            conexao.commit()
            falha += 1
            logger.warning("PDM %s falhou: %s", codigo, exc)
            continue

        guardar_precos(conexao, brutos)
        marcar_coletado(conexao, codigo, len(brutos))
        conexao.commit()

        registos += len(brutos)
        if brutos:
            sucesso += 1
        else:
            sem_compras += 1

    resultado = ResultadoDoLote(len(codigos), sucesso, sem_compras, falha, registos)
    logger.info(
        "lote concluído: %d PDMs, %d com compras, %d sem compras, %d falhas, %d registos",
        resultado.pdms,
        resultado.sucesso,
        resultado.sem_compras,
        resultado.falha,
        resultado.registos,
    )
    return resultado
