# 0006: a chave de comparacao inclui capacidade e unidade de medida

Data: 2026-08-21
Estado: aceito

## Contexto

Comparar precos exige saber o que conta como o mesmo produto. A primeira
versao da chave foi `codigo_item | unidade_fornecimento`, com o raciocinio de
que o mesmo codigo de catalogo aparece como AMPOLA e como COMPRIMIDO e que
separar por unidade de fornecimento resolvia isso.

Nao resolvia. **"FRASCO" nao e uma quantidade.**

Ao verificar o registro com a maior diferenca da lista de compras atipicas,
um unico `grupo_comparavel` de alcool etilico continha:

| unidade | capacidade | registros | mediana |
|---|---|---|---|
| FRASCO | 500 ML | 780 | R$ 5,62 |
| FRASCO | 1000 ML | 149 | R$ 8,30 |
| FRASCO | 100 ML | 22 | R$ 1,69 |
| FRASCO | 150 ML | 9 | R$ 24,78 |
| FRASCO | 400 G | 55 | R$ 6,20 |
| FRASCO | 1,7 KG | 8 | R$ 22,50 |

Frascos de 50 ML a 2 L no mesmo grupo, e volume misturado com massa. A
dispersao medida era em boa parte artefacto de tamanho, nao de preco.

**Dimensao do erro:** 781 dos 2.325 grupos com amostra util, 182.377
registros, 32% da base. A mediana do grupo do alcool passou de R$ 6,20 para
R$ 8,96 depois da correcao, ou seja, a referencia contra a qual toda a lista
de atipicas era calculada estava contaminada.

## Decisao

Duas chaves, com propositos distintos.

**`grupo_comparavel`**, estrita, para preco contra preco:
`codigo_item | unidade_fornecimento | capacidade_unidade | unidade_medida`.

**`grupo_normalizado`**, para preco por mililitro ou por grama:
`codigo_item | unidade_base`, com `preco_por_unidade_base`. As conversoes
sao dentro da mesma grandeza fisica: L e MCL vao para ML, KG, MG e MCG vao
para G. **Volume e massa nunca se convertem entre si.**

Metade dos registros (286.350) nao declara unidade de medida, e nesses a
capacidade vem a zero. Ficam com `unidade_base` e `preco_por_unidade_base`
nulos, em vez de assumir 1. Assumir inventaria dado.

## Consequencias

Os grupos passaram de 34.393 para 43.895, e os que tem amostra util (30 ou
mais registros) subiram de 2.325 para 4.293: a chave e mais fina, mas separar
tamanhos revelou grupos que antes estavam escondidos dentro de outros.

A lista de compras atipicas desceu de 8.102 para 7.772 registros, e as razoes
mudaram. O alcool com maior diferenca passou de 23,6x para 16,3x.

O teste `grupo_comparavel_nao_mistura_tamanhos` falha se alguem voltar a
simplificar a chave.

## Nota

E o mesmo erro do `VL_SA` na PoC Saude, noutra forma: **semantica de coluna
de fonte publica nao se infere do nome.** "FRASCO" parecia uma unidade
comparavel e nao era. Nos dois casos o defeito produzia numeros plausiveis,
e nos dois casos so apareceu ao verificar um registro concreto contra a
fonte, nunca ao olhar para o agregado.
