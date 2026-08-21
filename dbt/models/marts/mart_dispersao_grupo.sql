-- Dispersao de preco dentro do mesmo item e da mesma unidade, por ano.
--
-- Duas decisoes que mudam o resultado:
--
-- 1. Mediana, nao media. Um unico registro de R$ 21,9 milhoes num grupo cuja
--    mediana e R$ 3,28 arrasta qualquer media e nao arrasta a mediana.
--
-- 2. `percentile_disc` e nao `percentile_cont`. A versao continua devolve
--    `double precision` e interpola entre dois precos, inventando um valor
--    que ninguem pagou. A discreta devolve um preco realmente observado e
--    mantem o tipo `numeric`, que e o que dinheiro precisa.
--
-- 3. Corte em 30 registros. Abaixo disso a mediana do grupo oscila com um
--    unico contrato e a "dispersao" mede o tamanho da amostra, nao o
--    mercado. Os grupos pequenos ficam na tabela, marcados, para nao
--    desaparecerem em silencio: quem os quiser usar sabe o que esta a usar.

with por_grupo_ano as (
    select
        grupo_comparavel,
        codigo_item,
        codigo_pdm,
        max(nome_pdm)                                            as nome_pdm,
        unidade_fornecimento,
        capacidade_unidade,
        unidade_medida,
        extract(year from data_compra)::int                      as ano,
        count(*)                                                 as n_registros,
        count(distinct cnpj_fornecedor)                          as n_fornecedores,
        count(distinct codigo_uasg)                              as n_compradores,
        min(preco_unitario)                                      as preco_min,
        max(preco_unitario)                                      as preco_max,
        percentile_disc(0.25) within group (order by preco_unitario) as p25,
        percentile_disc(0.50) within group (order by preco_unitario) as mediana,
        percentile_disc(0.75) within group (order by preco_unitario) as p75
    from {{ ref('mart_precos') }}
    group by grupo_comparavel, codigo_item, codigo_pdm,
             unidade_fornecimento, capacidade_unidade, unidade_medida, ano
)

select
    *,
    n_registros >= 30 as amostra_suficiente,

    -- Quantas vezes o preco mais alto excede a mediana do proprio grupo.
    -- Nulo quando a mediana e zero, em vez de divisao por zero disfarcada.
    case when mediana > 0 then round(preco_max / mediana, 2) end
        as razao_max_mediana,

    -- Amplitude interquartil relativa: mede a dispersao do miolo do grupo,
    -- sem depender dos extremos. Complementa a razao acima, que so olha
    -- para o pior caso.
    case when mediana > 0 then round((p75 - p25) / mediana, 4) end
        as dispersao_interquartil
from por_grupo_ano
