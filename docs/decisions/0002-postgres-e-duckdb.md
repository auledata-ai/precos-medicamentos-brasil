# ADR 0002: Postgres para ingestão, DuckDB para análise

**Data:** 2026-08-21 · **Estado:** aceite

## Contexto

O universo estimado é de cerca de 490 mil registos de preço, medido por
amostragem contra a API real. É um volume pequeno.

## Decisão

Postgres 16 para as camadas raw e staging. DuckDB sobre parquet para a
camada analítica.

## Porquê não distribuído

490 mil linhas cabem com folga em memória de um portátil. Spark ou qualquer
motor distribuído aqui adicionaria latência de arranque, complexidade
operacional e uma narrativa falsa sobre o problema.

Já cometemos o erro inverso num projeto anterior: descrever camadas de
lakehouse num pipeline que era pandas local. O leitor técnico nota, e o custo
é credibilidade.

## Porquê Postgres na ingestão

A ingestão precisa de escrita transacional com `upsert` por chave natural,
para ser idempotente, e de uma tabela de controlo consultada e atualizada a
cada item. É carga transacional, e é o que Postgres faz bem.

## Porquê DuckDB na análise

As consultas analíticas são varreduras colunares com agregação por grupo.
DuckDB executa isso sobre parquet em milissegundos, sem servidor, e o
ficheiro resultante é versionável e distribuível junto com o estudo.

## Consequências

- Há duas tecnologias de armazenamento, com uma fronteira a manter clara:
  Postgres é escrita, DuckDB é leitura.
- A materialização de Postgres para parquet vira uma etapa explícita da DAG,
  não um efeito colateral.
