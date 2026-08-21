-- Itens de medicamento do catalogo federal.
select
    codigo_item,
    (payload ->> 'codigoPdm')      as codigo_pdm,
    (payload ->> 'nomePdm')        as nome_pdm,
    (payload ->> 'descricaoItem')  as descricao_item,
    (payload ->> 'codigoClasse')::int as codigo_classe,
    (payload ->> 'nomeClasse')     as nome_classe,
    coletado_em
from {{ source('raw', 'catalogo') }}
