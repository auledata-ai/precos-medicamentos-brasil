# ADR 0005: Coletar por PDM, não por item de catálogo

**Data:** 2026-08-21 · **Estado:** aceite · **Substitui parte do:** ADR 0003

## Contexto

A primeira coleta completa falhou 14% dos itens com HTTP 429. Ao investigar,
medimos três coisas contra a API real:

- A fonte devolve `Retry-After: 42` no 429. O nosso teto de recuo era 30
  segundos, portanto voltávamos sempre antes do permitido.
- O limite é de **concorrência**, não de taxa sustentada. Sequencial a 0,5
  segundos passa sem bloqueio; oito pedidos simultâneos bloqueiam de imediato.
- Sequencial rende cerca de 0,36 pedidos por segundo, porque cada resposta
  demora perto de dois segundos. Para 12.359 itens seriam quase nove horas.

## Decisão

Coletar por `codigoPdm` em vez de `codigoItemCatalogo`.

## Porquê

O PDM (Padrão Descritivo de Material) agrupa itens equivalentes. A classe de
medicamentos tem **12.359 itens** e apenas **1.878 PDMs**, uma redução de
6,6 vezes no número de chamadas.

Verificámos que a consulta por PDM devolve um **superconjunto** da consulta
por item: para o PDM 348, vieram 588 registos cobrindo 3 itens, e todos os 42
registos da consulta por item 354314 estavam lá.

O tempo de coleta completa cai de cerca de nove horas para pouco mais de uma.

## Consequências

- A tabela de controlo passa a ter uma linha por PDM, não por item. Menos
  linhas, e a unidade de retomada passa a ser o PDM.
- A cobertura publicada passa a ser em PDMs. Itens continuam a existir na
  camada raw, porque cada registo de preço traz o seu `codigoItemCatalogo`.
- Um PDM com muitos itens pode ultrapassar as 500 linhas por página. A
  paginação já trata disso; não há mudança necessária.
- Se a fonte alterar o agrupamento por PDM, a cobertura muda sem aviso. O
  teste de contrato deve verificar que a consulta por PDM continua a devolver
  mais do que a consulta por item equivalente.
