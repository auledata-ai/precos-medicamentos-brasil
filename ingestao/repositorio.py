"""Persistência da camada raw e do controlo de ingestão.

Todo o SQL vive aqui. As funções recebem a ligação, não a criam: assim o
chamador controla a transação, e os testes correm dentro de uma que é
revertida no fim.

Escrita sempre por `upsert` sobre a chave natural. Um `insert` cego tornaria
a reexecução destrutiva, e a reexecução é o caso normal, não a excepção.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ingestao.coleta import RegistoBruto

ESQUEMA = Path(__file__).parent / "sql" / "esquema.sql"

# Quanto tempo uma coleta continua válida. A fonte atualiza continuamente,
# portanto "já coletado alguma vez" não pode significar "nunca mais coletar":
# o estudo congelaria no dia da primeira execução.
VALIDADE_PADRAO = timedelta(days=7)


def ligar(dsn: str | None = None) -> psycopg.Connection:
    """Ligação ao Postgres. O DSN vem do ambiente, nunca do código."""
    dsn = dsn or os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("POSTGRES_DSN não definido. Exporte a variável ou passe o dsn.")
    return psycopg.connect(dsn, row_factory=dict_row)


def criar_esquema(conexao: psycopg.Connection) -> None:
    """Idempotente: todo o DDL usa `if not exists`."""
    conexao.execute(ESQUEMA.read_text())


@dataclass(frozen=True)
class Cobertura:
    """Retrato da coleta. Estes números são observabilidade e conteúdo."""

    total: int
    sucesso: int
    sem_compras: int
    falha: int
    pendente: int
    registos: int


def _texto(valor: Any) -> str:
    return str(valor)


def guardar_catalogo(conexao: psycopg.Connection, registos: list[RegistoBruto]) -> int:
    """Grava itens do catálogo e cria a linha de controlo de cada PDM.

    O controlo é por PDM e não por item: um PDM agrupa itens equivalentes e
    uma só chamada traz os preços de todos (ver ADR 0005).

    A linha nasce 'pendente' e nunca é rebaixada por uma recoleta do
    catálogo: um PDM já coletado com sucesso não volta a pendente só porque
    o catálogo foi lido de novo.
    """
    if not registos:
        return 0
    linhas = [
        (
            _texto(r.payload["codigoItem"]),
            json.dumps(r.payload, ensure_ascii=False),
            r.hash_payload,
            r.endpoint,
            json.dumps(r.parametros, ensure_ascii=False),
            r.coletado_em,
        )
        for r in registos
    ]
    with conexao.cursor() as cur:
        cur.executemany(
            """
            insert into raw.catalogo
                (codigo_item, payload, hash_payload, endpoint, parametros, coletado_em)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (codigo_item) do update set
                payload      = excluded.payload,
                hash_payload = excluded.hash_payload,
                coletado_em  = excluded.coletado_em
            """,
            linhas,
        )
        pdms = {
            _texto(r.payload["codigoPdm"])
            for r in registos
            if r.payload.get("codigoPdm") is not None
        }
        cur.executemany(
            """
            insert into raw.controlo_ingestao (codigo_pdm)
            values (%s)
            on conflict (codigo_pdm) do nothing
            """,
            [(pdm,) for pdm in sorted(pdms)],
        )
    return len(linhas)


def guardar_precos(conexao: psycopg.Connection, registos: list[RegistoBruto]) -> int:
    """Grava preços pela chave natural (idCompra, idItemCompra).

    O `codigo_item` vem de cada registo e não do parâmetro da consulta: uma
    coleta por PDM traz preços de vários itens diferentes.
    """
    if not registos:
        return 0
    linhas = [
        (
            _texto(r.payload["idCompra"]),
            _texto(r.payload["idItemCompra"]),
            _texto(r.payload["codigoItemCatalogo"]),
            json.dumps(r.payload, ensure_ascii=False),
            r.hash_payload,
            r.endpoint,
            json.dumps(r.parametros, ensure_ascii=False),
            r.coletado_em,
        )
        for r in registos
    ]
    with conexao.cursor() as cur:
        cur.executemany(
            """
            insert into raw.precos
                (id_compra, id_item_compra, codigo_item, payload, hash_payload,
                 endpoint, parametros, coletado_em)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id_compra, id_item_compra) do update set
                payload      = excluded.payload,
                hash_payload = excluded.hash_payload,
                coletado_em  = excluded.coletado_em
            """,
            linhas,
        )
    return len(linhas)


def marcar_coletado(conexao: psycopg.Connection, codigo_pdm: str, registos_obtidos: int) -> None:
    """Item coletado com sucesso.

    Zero registos é 'sem_compras', não falha: metade do catálogo não tem
    compra alguma, e tratar isso como erro encheria o log de ruído e faria
    o pipeline repetir eternamente itens que nunca terão dados.
    """
    estado = "sucesso" if registos_obtidos else "sem_compras"
    conexao.execute(
        """
        update raw.controlo_ingestao
           set coletado_em = %s, registos_obtidos = %s, estado = %s,
               erro = null, atualizado_em = now()
         where codigo_pdm = %s
        """,
        (datetime.now(UTC), registos_obtidos, estado, _texto(codigo_pdm)),
    )


def marcar_falha(conexao: psycopg.Connection, codigo_pdm: str, erro: str) -> None:
    """Falha registada com o motivo, e o contador de tentativas incrementado.

    `coletado_em` NÃO é tocado: a falha não invalida a última coleta boa.
    """
    conexao.execute(
        """
        update raw.controlo_ingestao
           set estado = 'falha', erro = %s,
               tentativas = tentativas + 1, atualizado_em = now()
         where codigo_pdm = %s
        """,
        (erro[:500], _texto(codigo_pdm)),
    )


def pdms_pendentes(
    conexao: psycopg.Connection,
    validade: timedelta = VALIDADE_PADRAO,
    limite: int | None = None,
    forcar: bool = False,
    max_tentativas: int = 3,
) -> list[str]:
    """PDMs a coletar nesta execução.

    Pendente é o que nunca foi coletado, ou foi há mais do que `validade`.
    PDMs que falharam repetidamente saem da fila: sem esse limite, um PDM
    que a fonte nunca consegue servir seria repetido em todas as execuções,
    para sempre.

    `forcar` ignora tudo e devolve o catálogo inteiro. É a única forma de
    recoletar deliberadamente, e é explícita de propósito.
    """
    if forcar:
        sql = "select codigo_pdm from raw.controlo_ingestao order by codigo_pdm"
        parametros: tuple = ()
    else:
        sql = """
            select codigo_pdm
              from raw.controlo_ingestao
             where tentativas < %s
               and (coletado_em is null or coletado_em < %s)
             order by coletado_em nulls first, codigo_pdm
        """
        parametros = (max_tentativas, datetime.now(UTC) - validade)
    if limite is not None:
        sql += " limit %s"
        parametros = (*parametros, limite)
    with conexao.cursor() as cur:
        cur.execute(sql, parametros)
        return [linha["codigo_pdm"] for linha in cur.fetchall()]


def cobertura(conexao: psycopg.Connection) -> Cobertura:
    with conexao.cursor() as cur:
        cur.execute(
            """
            select count(*) as total,
                   count(*) filter (where estado = 'sucesso')     as sucesso,
                   count(*) filter (where estado = 'sem_compras') as sem_compras,
                   count(*) filter (where estado = 'falha')       as falha,
                   count(*) filter (where estado = 'pendente')    as pendente,
                   coalesce(sum(registos_obtidos), 0)             as registos
              from raw.controlo_ingestao
            """
        )
        return Cobertura(**cur.fetchone())
