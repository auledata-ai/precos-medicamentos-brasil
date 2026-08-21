"""DAG do pipeline de preços de medicamentos, da fonte ao número publicado.

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
  transformar     Corre o dbt depois da coleta. Desligar serve para ensaiar
                  a ingestão sozinha, não para uso normal.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.models.param import Param
from airflow.utils.trigger_rule import TriggerRule
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
    "transformar": Param(True, type="boolean"),
}

# O projeto inteiro esta montado aqui dentro do container.
PROJETO = Path("/opt/airflow/projeto")


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

    # `none_failed` e nao a regra por omissao: quando nao ha nada para
    # coletar, `lotes` devolve lista vazia, `precos` nao expande, e o skip
    # cascateia por toda a arvore. O run acabava verde sem ter transformado
    # nem publicado nada, que e o pior resultado possivel: falha silenciosa
    # disfarcada de sucesso.
    @task.short_circuit(trigger_rule=TriggerRule.NONE_FAILED)
    def deve_transformar(**contexto) -> bool:
        """Corta o ramo de transformação quando o parâmetro pede."""
        return bool(contexto["params"]["transformar"])

    @task
    def transformar() -> dict:
        """Constrói os modelos dbt e corre os testes.

        `dbt build` e não `dbt run`: constrói e testa na mesma passagem, e
        para no primeiro modelo cujo teste falha. Separar os dois deixaria
        marts publicadas antes de alguém olhar para o resultado dos testes.

        O código de saída do dbt é o que decide o estado da task. Ler o log
        à procura de "Completed successfully" seria depender de uma frase.
        """
        processo = subprocess.run(
            ["dbt", "build", "--project-dir", str(PROJETO / "dbt")],
            capture_output=True,
            text=True,
            check=False,
        )
        cauda = processo.stdout.strip().splitlines()[-15:]
        if processo.returncode != 0:
            raise RuntimeError(
                "dbt build falhou:\n" + "\n".join(cauda) + "\n" + processo.stderr[-1000:]
            )
        return {"saida": processo.returncode, "resumo": cauda[-1] if cauda else ""}

    @task
    def publicar() -> dict:
        """Recalcula os números publicáveis e escreve-os no repositório.

        É o passo que fecha o ciclo: sem ele, os modelos mudam e o JSON que
        alimenta os gráficos continua a mostrar a versão anterior, sem que
        nada acuse a diferença.
        """
        from analise import graficos
        from analise.resultados import tudo as resultados_de
        from ingestao.repositorio import ligar

        destino = PROJETO / "docs" / "dados"
        destino.mkdir(parents=True, exist_ok=True)
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            saidas = {
                "resultados.json": resultados_de(conexao),
                "graficos.json": graficos.tudo(conexao),
            }
        for nome, conteudo in saidas.items():
            (destino / nome).write_text(
                json.dumps(conteudo, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return {"arquivos": sorted(saidas)}

    @task(trigger_rule=TriggerRule.NONE_FAILED)
    def relatorio(resultados: list[dict]) -> dict:
        """Consolida a execução. Estes números são observabilidade e conteúdo.

        Corre mesmo quando não houve nada a coletar: uma execução sem itens
        pendentes é um resultado legítimo, e precisa de aparecer no relatório
        como zero em vez de desaparecer.
        """
        with ligar(os.environ["POSTGRES_DSN"]) as conexao:
            atual = cobertura(conexao)
        total = {
            chave: sum(r[chave] for r in resultados or [])
            for chave in ("pdms", "sucesso", "sem_compras", "falha", "registros")
        }
        return {"execucao": total, "acumulado": atual.__dict__}

    fim_da_coleta = relatorio(precos.expand(codigos=lotes()))
    preparar_esquema() >> catalogo() >> fim_da_coleta
    fim_da_coleta >> deve_transformar() >> transformar() >> publicar()


coleta_precos_medicamentos()
