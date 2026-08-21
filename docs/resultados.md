# O que estes dados respondem

Todos os números deste documento saem de `dados/resultados.json`, gerado por
`uv run python -m analise`. Nenhum foi copiado à mão.

## A base

563.881 registos de compras públicas de medicamentos, de 44.354 processos,
7.157 fornecedores e 965 municípios, entre dezembro de 2020 e julho de 2026.
Fonte: API de pesquisa de preços do Compras.gov.br.

Foram excluídos 8.671 registos, 1,51% do total:

| motivo | registos | % |
|---|---|---|
| sem unidade de fornecimento | 8.450 | 1,4758 |
| sem data de compra | 202 | 0,0353 |
| quantidade inválida | 22 | 0,0038 |
| preço não positivo | 3 | 0,0005 |

Seis registos falham mais de uma regra, por isso a soma da coluna é maior
que o total de excluídos.

## Achado 1: o mercado comum é mais apertado do que se supõe

Comparando apenas preços do mesmo produto, mesmo tamanho de embalagem,
mesma unidade de medida e mesmo ano, em 4.293 grupos com pelo menos 30
registos:

| | razão entre o percentil 75 e o 25 |
|---|---|
| primeiro quartil dos grupos | 1,27x |
| **mediana dos grupos** | **1,42x** |
| terceiro quartil | 1,68x |
| percentil 90 | 2,22x |

No grupo típico, uma compra cara custa 42% mais do que uma barata. É
dispersão, não é escândalo. Compras públicas variam por prazo de entrega,
quantidade mínima, logística e condição de pagamento, e uma diferença desta
ordem é compatível com essas causas.

## Achado 2: a cauda extrema é um padrão de registo, não um preço

Existem 288 registos acima de 1.000 vezes a mediana do próprio grupo.
Sinvastatina a R$ 750.000. Azitromicina a R$ 3.000.000. Ácido
acetilsalicílico a R$ 253.300.

Nenhum é um comprimido caro. **70,8% desses registos têm quantidade igual
a 1**, contra 0,50% na base inteira. É uma concentração de 143 vezes.

A assinatura é de compra inteira lançada como uma única unidade: o valor do
contrato entra no campo de preço unitário e a quantidade fica em 1.

A intensidade do padrão acompanha a gravidade do desvio:

| faixa | registos | com quantidade 1 |
|---|---|---|
| 1.000x ou mais | 288 | 70,8% |
| 100x a 1.000x | 1.340 | 11,6% |
| 10x a 100x | 6.144 | 3,6% |

Uma hipótese alternativa foi testada e descartada: se fosse o valor do lote
dividido mal, `preço / quantidade` cairia perto da mediana do grupo. Isso
acontece em apenas 9,2% dos casos acima de 100x.

## Achado 3: o dinheiro não está nos absurdos

Nos grupos com amostra suficiente, o gasto somado é de R$ 45,60 bilhões, e
R$ 2,34 bilhões ficaram acima da mediana do próprio grupo, 5,14%.

A objeção óbvia é que os valores absurdos do achado 2 estariam a puxar o
total. Não estão:

| cenário | gasto | acima da mediana | % |
|---|---|---|---|
| todos os registos | R$ 45,60 bi | R$ 2,34 bi | 5,14 |
| sem os acima de 1.000x | R$ 45,55 bi | R$ 2,30 bi | 5,04 |
| sem os acima de 100x | R$ 45,52 bi | R$ 2,27 bi | 4,98 |

Remover tudo acima de 100 vezes a mediana muda o resultado em 0,16 ponto
percentual. **A diferença vem do meio da distribuição, não das pontas.**

## O que estes números não dizem

**Não são prejuízo.** A coluna chama-se `diferenca_para_a_mediana` porque é
isso que ela mede: a distância a uma referência interna. Pagar acima da
mediana tem explicações legítimas, e uma compra de urgência para um
município distante deve mesmo custar mais.

**Não identificam fraude.** Um preço alto é uma pergunta, não uma resposta.
A lista de 7.772 compras atípicas serve para reduzir 564 mil registos a algo
que uma pessoa consegue olhar, com o contexto necessário para julgar cada
caso: comprador, fornecedor, data, quantidade, modalidade e o grupo de
comparação que produziu a razão.

**Não cobrem a compra pública inteira.** Só entram itens com pelo menos 30
registos comparáveis no mesmo ano: 4.293 grupos dos 43.895 existentes. Os
outros não têm base para comparação, e inventá-la seria pior do que
admitir a lacuna.

## Ressalva metodológica

A definição de "mesmo produto" é a decisão que mais afeta estes números, e
a primeira versão dela estava errada. O ADR 0006 documenta o erro, a sua
dimensão e a correção.
