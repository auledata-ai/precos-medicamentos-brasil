-- Compras muito acima da mediana do proprio grupo, no mesmo ano.
--
-- Esta tabela nao acusa ninguem. Um preco alto tem explicacoes legitimas:
-- compra de urgencia, quantidade minima, logistica para municipio remoto,
-- registo de preco de lote lancado como unitario. O que ela faz e reduzir
-- 564 mil registos a uma lista curta que vale a pena olhar, e dar o
-- contexto necessario para julgar cada caso.
--
-- O criterio e a razao para a mediana do grupo, e nao um desvio padrao:
-- precos sao muito assimetricos a direita e o desvio padrao e ele proprio
-- arrastado pelos extremos que queremos encontrar.
--
-- O corte de 10x e uma escolha, nao um facto. Fica explicito aqui e a
-- coluna `razao_mediana` permite refazer a lista com outro corte.

{% set corte_razao = 10 %}

with base as (
    select
        p.*,
        d.mediana                as mediana_do_grupo,
        d.n_registos             as n_registos_do_grupo,
        d.n_fornecedores         as n_fornecedores_do_grupo,
        d.amostra_suficiente
    from {{ ref('mart_precos') }} p
    join {{ ref('mart_dispersao_grupo') }} d
        on p.grupo_comparavel = d.grupo_comparavel
       and extract(year from p.data_compra)::int = d.ano
    where d.amostra_suficiente
      and d.mediana > 0
)

select
    id_compra,
    id_item_compra,
    -- O grupo vem junto de proposito: sem ele nao se consegue reconstruir a
    -- referencia que produziu a razao, e uma lista que nao se consegue
    -- auditar nao devia ser publicada.
    grupo_comparavel,
    codigo_item,
    nome_pdm,
    descricao_item,
    unidade_fornecimento,
    capacidade_unidade,
    unidade_medida,
    data_compra,
    uf,
    municipio,
    unidade_compradora,
    esfera,
    poder,
    fornecedor,
    cnpj_fornecedor,
    marca,
    modalidade,
    quantidade,
    preco_unitario,
    mediana_do_grupo,
    round(preco_unitario / mediana_do_grupo, 2) as razao_mediana,

    -- Quanto se teria pago a mais face a mediana do grupo. E uma diferenca
    -- face a uma referencia, nao um prejuizo apurado.
    round((preco_unitario - mediana_do_grupo) * quantidade, 2)
        as diferenca_para_a_mediana,

    n_registos_do_grupo,
    n_fornecedores_do_grupo
from base
where preco_unitario / mediana_do_grupo >= {{ corte_razao }}
order by diferenca_para_a_mediana desc
