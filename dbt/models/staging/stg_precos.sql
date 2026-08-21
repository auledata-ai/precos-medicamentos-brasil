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
),

normalizado as (
    select
        *,
        -- Conversao para uma base comum dentro da mesma grandeza fisica.
        -- Volume e massa nao se convertem entre si e ficam separados: 500 ML
        -- e 500 G do mesmo codigo sao produtos diferentes.
        case upper(coalesce(unidade_medida, ''))
            when 'ML'  then 'ML'
            when 'L'   then 'ML'
            when 'MCL' then 'ML'
            when 'G'   then 'G'
            when 'KG'  then 'G'
            when 'MG'  then 'G'
            when 'MCG' then 'G'
            when 'UI'  then 'UI'
            when 'KUI' then 'UI'
            when 'DOSE(S)' then 'DOSE'
            when 'DOSES'   then 'DOSE'
            when 'UN'  then 'UN'
            -- Metade dos registros nao declara unidade, e nesses a capacidade
            -- vem a zero. Ficam nulos: sem grandeza declarada nao ha como
            -- normalizar, e arbitrar uma inventaria dado.
            else null
        end as unidade_base,
        case upper(coalesce(unidade_medida, ''))
            when 'L'   then capacidade_unidade * 1000
            when 'MCL' then capacidade_unidade / 1000
            when 'KG'  then capacidade_unidade * 1000
            when 'MG'  then capacidade_unidade / 1000
            when 'MCG' then capacidade_unidade / 1000000
            when 'KUI' then capacidade_unidade * 1000
            when ''    then null
            else capacidade_unidade
        end as capacidade_base
    from tipado
)

select
    *,
    -- Chave de comparacao estrita, para preco contra preco.
    --
    -- A versao anterior era so `codigo_item | unidade_fornecimento`, e isso
    -- estava errado: "FRASCO" nao e uma quantidade. Um unico grupo continha
    -- frascos de 50 ML a 2 L, e ate ML misturado com G, o que fabricava
    -- dispersao onde ha apenas tamanhos diferentes. Afetava 781 dos 2.325
    -- grupos com amostra util, 182 mil registros. A capacidade e a unidade
    -- entram na chave por isso.
    codigo_item
        || '|' || coalesce(unidade_fornecimento, 'SEM_UNIDADE')
        || '|' || coalesce(capacidade_unidade::text, 'SEM_CAPACIDADE')
        || '|' || coalesce(unidade_medida, 'SEM_MEDIDA')
        as grupo_comparavel,

    -- Chave de comparacao normalizada, para preco por mililitro ou por
    -- grama. Permite comparar tamanhos diferentes do mesmo produto sem os
    -- confundir, que e o que a chave estrita nao faz.
    case when unidade_base is not null
        then codigo_item || '|' || unidade_base
    end as grupo_normalizado,

    -- Preco por unidade da base comum. Nulo quando nao ha capacidade
    -- declarada, em vez de assumir 1: assumir inventaria dado.
    case when capacidade_base > 0
        then preco_unitario / capacidade_base
    end as preco_por_unidade_base
from normalizado
