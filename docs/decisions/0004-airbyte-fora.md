# ADR 0004: Sem Airbyte

**Data:** 2026-08-21 · **Estado:** aceite

## Contexto

Airbyte foi considerado para a camada de ingestão, por ser a escolha
convencional em stacks abertas modernas.

## Decisão

Não usar. A ingestão é um módulo Python chamado pelo Airflow.

## Porquê

Airbyte compensa quando há muitas fontes heterogéneas e conectores prontos
que poupam trabalho real. Aqui há **uma** fonte, com paginação específica,
parâmetros obrigatórios peculiares e armadilhas documentadas: `tamanhoPagina`
tem de ser 500 senão o filtro de classe é ignorado em silêncio, e o tipo de
consulta é um enum não óbvio.

Um conector genérico teria de ser configurado para tudo isso, e o resultado
seria configuração em YAML de um comportamento que se escreve em vinte linhas
de Python testável.

## Consequências

- Perdemos a interface visual de ingestão, que ninguém aqui ia usar.
- Ganhamos testes unitários sobre a lógica de coleta, sem subir serviço.
- Se um dia houver cinco fontes, a decisão deve ser revista.
