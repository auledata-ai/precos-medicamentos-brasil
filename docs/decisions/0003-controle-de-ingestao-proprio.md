# ADR 0003: Tabela de controle de ingestão própria

**Data:** 2026-08-21 · **Estado:** aceito

## Contexto

A ingestão percorre cerca de 6.600 itens. A execução vai falhar a meio, por
erro da fonte, por rede ou por interrupção. Precisamos de saber o que já foi
coletado.

## Decisão

Uma tabela `controle_ingestao` em Postgres, com uma linha por item de
catálogo: identificador, instante da última coleta bem sucedida, número de
registros obtidos, e estado da última tentativa.

## Porquê não confiar no estado do Airflow

O Airflow sabe se uma **task** correu, não se um **item** foi coletado. Uma
task que processa 500 itens e falha no 300 aparece como falhada por inteiro,
e reexecutá-la recoletaria os 300 primeiros.

Além disso, os metadados do Airflow são infraestrutura descartável. Recriar o
ambiente não pode implicar duas horas de recoleta.

## Consequências

- A retomada é responsabilidade do nosso código, não do orquestrador. É mais
  código, e é o código certo.
- A tabela dá observabilidade de graça: cobertura da coleta, itens sem
  compra, taxa de falha por item. Esses números são conteúdo publicável.
- Reprocessamento forçado precisa de um parâmetro explícito que ignore o
  controle. Sem ele, reexecutar não recoleta nada, o que é o comportamento
  desejado por omissão.
