"""DAG de coleta de preços de medicamentos.

Deliberadamente fina: não contém lógica de negócio. Cada task chama uma
função de `ingestao.execucao`, que é testável sem Airflow. Se algum dia for
preciso escrever lógica aqui, a fronteira das camadas ficou no sítio errado.

Parâmetros da execução, todos com default explícito:

  validade_dias   Quanto tempo uma coleta continua válida. Abaixo disto o
                  item não é recoletado.
  n_lotes         Lotes paralelos. O teto útil é o limite de taxa da fonte,
                  não a nossa capacidade.
  limite          Máximo de itens nesta execução. Útil para ensaiar.
  forcar          Ignora o controle e recoleta tudo. Explícito de propósito.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.models.param import Param
from ingestao.cliente import Cliente
from ingestao.execucao import coletar_lote, planear_lotes, sincronizar_catalogo
from ingestao.repositorio import cobertura, criar_esquema, ligar

# Params tipados, e nao um dicionario simples: o `--conf` da linha de comandos
# entrega os valores como texto, e sem tipo declarado um "2" chegaria como
# string a `planear_lotes`, que compara com inteiro.
DEFAULTS = {
    "validade_dias": Param(7, type="integer", minimum=0),
    "n_lotes": Param(4, type="integer", minimum=1, maximum=16),
    "limite": Param(None, type=["null", "integer"], minimum=1),
    "forcar": Param(False, type="boolean"),
}


@dag(
    dag_id="coleta_precos_medicamentos",
    description="Coleta preços de medicamentos comprados pelo setor público",
    # Semanal: a fonte atualiza continuamente, mas o estudo nao precisa de
    # latencia menor, e cada execucao completa custa cerca de duas horas.
    schedule="0 3 * * 1",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
    params=DEFAULTS,
    tags=["compras", "medicamentos", "aule"],
)
def coleta_precos_medicamentos():
    @task
    def preparar_esquema() -> None:
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            criar_esquema(conexao)
            conexao.commit()

    @task
    def catalogo() -> int:
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            return sincronizar_catalogo(Cliente(), conexao)

    @task
    def lotes(**contexto) -> list[list[str]]:
        p = contexto["params"]
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            return planear_lotes(
                conexao,
                n_lotes=p["n_lotes"],
                validade=timedelta(days=p["validade_dias"]),
                limite=p["limite"],
                forcar=p["forcar"],
            )

    @task(max_active_tis_per_dag=4)
    def precos(codigos: list[str]) -> dict:
        # Um cliente por task: o limitador de taxa guarda estado proprio e
        # nao e seguro partilhar entre processos.
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            return coletar_lote(Cliente(), conexao, codigos).__dict__

    @task
    def relatorio(resultados: list[dict]) -> dict:
        """Consolida a execução. Estes números são observabilidade e conteúdo."""
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            atual = cobertura(conexao)
        total = {
            chave: sum(r[chave] for r in resultados)
            for chave in ("pdms", "sucesso", "sem_compras", "falha", "registros")
        }
        return {"execucao": total, "acumulado": atual.__dict__}

    preparar_esquema() >> catalogo() >> relatorio(precos.expand(codigos=lotes()))


coleta_precos_medicamentos()
