-- Registos que nao podem entrar na analise, com o motivo de cada um.
--
-- A regra e sempre a mesma: excluir so o que impede a comparacao, nunca o
-- que parece estranho. Um preco muito acima da mediana do grupo e o achado
-- do estudo, nao um defeito, e por isso nao aparece aqui.
--
-- Cada registo leva todos os motivos que o atingem, nao apenas o primeiro.
-- Contar "202 sem data" e "22 com quantidade invalida" como se fossem
-- conjuntos disjuntos daria um total errado se houver sobreposicao.

with avaliado as (
    select
        id_compra,
        id_item_compra,
        codigo_item,
        codigo_pdm,
        preco_unitario,
        quantidade,
        data_compra,
        unidade_fornecimento,
        array_remove(
            array[
                case when preco_unitario is null
                    then 'preco_ausente' end,
                case when preco_unitario <= 0
                    then 'preco_nao_positivo' end,
                case when data_compra is null
                    then 'sem_data_de_compra' end,
                case when quantidade is null or quantidade <= 0
                    then 'quantidade_invalida' end,
                -- Sem unidade de fornecimento nao ha grupo comparavel: o
                -- mesmo codigo aparece como AMPOLA e como COMPRIMIDO, e
                -- juntar os dois produz uma dispersao que e artefacto.
                case when unidade_fornecimento is null
                    then 'sem_unidade_de_fornecimento' end
            ],
            null
        ) as motivos
    from {{ ref('stg_precos') }}
)

select
    id_compra,
    id_item_compra,
    codigo_item,
    codigo_pdm,
    preco_unitario,
    quantidade,
    data_compra,
    unidade_fornecimento,
    motivos,
    array_length(motivos, 1) as n_motivos
from avaliado
where array_length(motivos, 1) > 0
