-- Tipagem e normalizacao. Nenhuma regra de negocio: a decisao sobre o que e
-- preco plausivel pertence a quarentena, nao aqui.
--
-- A normalizacao de unidade e o ponto critico deste modelo. O mesmo
-- codigo de catalogo aparece como AMPOLA de 2 ML e como COMPRIMIDO, e
-- comparar precos sem separar por unidade produz numeros falsos.

with bruto as (
    select
        id_compra,
        id_item_compra,
        codigo_item,
        payload,
        coletado_em
    from {{ source('raw', 'precos') }}
),

tipado as (
    select
        id_compra,
        id_item_compra,
        codigo_item,
        (payload ->> 'codigoPdm')                        as codigo_pdm,
        (payload ->> 'nomePdm')                          as nome_pdm,
        (payload ->> 'descricaoItem')                    as descricao_item,

        -- Dinheiro em numeric, nunca em float: somar centenas de milhares de
        -- valores em ponto flutuante acumula erro.
        (payload ->> 'precoUnitario')::numeric(14, 4)    as preco_unitario,
        (payload ->> 'quantidade')::numeric(16, 4)       as quantidade,

        (payload ->> 'nomeUnidadeFornecimento')          as unidade_fornecimento,
        nullif(payload ->> 'capacidadeUnidadeFornecimento', '')::numeric
                                                         as capacidade_unidade,
        (payload ->> 'siglaUnidadeMedida')               as unidade_medida,

        (payload ->> 'dataCompra')::date                 as data_compra,
        (payload ->> 'codigoMunicipio')                  as codigo_municipio,
        (payload ->> 'municipio')                        as municipio,
        (payload ->> 'estado')                           as uf,
        (payload ->> 'esfera')                           as esfera,
        (payload ->> 'poder')                            as poder,
        (payload ->> 'codigoUasg')                       as codigo_uasg,
        (payload ->> 'nomeUasg')                         as unidade_compradora,
        (payload ->> 'nomeFornecedor')                   as fornecedor,
        (payload ->> 'niFornecedor')                     as cnpj_fornecedor,
        (payload ->> 'marca')                            as marca,
        (payload ->> 'modalidade')                       as modalidade,
        coletado_em
    from bruto
)

select
    *,
    -- Chave de comparacao. So faz sentido comparar precos dentro do mesmo
    -- item E da mesma unidade de fornecimento.
    codigo_item || '|' || coalesce(unidade_fornecimento, 'SEM_UNIDADE')
        as grupo_comparavel,

    -- Preco por unidade de medida, quando a capacidade e conhecida. Permite
    -- comparar uma ampola de 2 ML com uma de 10 ML. Quando nao ha
    -- capacidade, fica nulo em vez de assumir 1: assumir inventaria dado.
    case
        when capacidade_unidade > 0 then preco_unitario / capacidade_unidade
    end as preco_por_unidade_medida
from tipado
