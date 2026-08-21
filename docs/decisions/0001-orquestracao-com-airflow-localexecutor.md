# ADR 0001: Airflow com LocalExecutor

**Data:** 2026-08-21 · **Estado:** aceite

## Contexto

A ingestão exige cerca de 6.600 chamadas HTTP, uma por item de catálogo com
compra registada. A uma chamada por segundo são aproximadamente duas horas.
A fonte atualiza continuamente, o que torna a carga recorrente.

## Decisão

Airflow 2.10 com LocalExecutor, em Docker Compose.

## Porquê Airflow

A alternativa honesta era um script com `cron`. Foi descartada por quatro
necessidades que o script obrigaria a reimplementar:

- **Retomada**: 6.600 chamadas falham no meio. Reexecutar do zero custa duas
  horas por falha.
- **Retentativa com recuo**: a API pública vai devolver 5xx e limitar taxa.
- **Carga incremental e backfill**: a fonte atualiza; queremos processar só o
  novo, e poder reprocessar um intervalo passado.
- **Dependência entre etapas**: catálogo antes de preços, preços antes de
  qualidade, qualidade antes de agregação.

Este é o critério que aplicamos: orquestrador entra quando há atualização
recorrente real, dependência entre tarefas e falha esperada. Num pipeline
que roda duas vezes por ano, seria teatro de arquitetura.

## Porquê LocalExecutor e não Celery

A carga é limitada por rede, não por CPU, e o paralelismo útil é modesto:
acima de poucas chamadas simultâneas passamos a bater no limite de taxa da
fonte, não na nossa capacidade.

Celery acrescentaria Redis, workers e flower. Numa máquina de 7,7 GB isso é
memória gasta em coordenação de trabalho que não existe.

## Consequências

- O paralelismo fica limitado ao número de processos do container. Aceitável,
  porque o teto real é a fonte.
- Escalar horizontalmente exigiria trocar de executor. Não é previsto.
- O estado do Airflow **não** é a fonte de verdade da retomada. Uma tabela de
  controlo própria regista o que já foi coletado (ver ADR 0003), porque
  limpar metadados do Airflow não pode significar recoletar tudo.
