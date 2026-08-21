-- O que esta em quarentena nao pode estar na base da analise. Se o anti-join
-- do `mart_precos` se partir, as duas tabelas passam a somar mais do que o
-- staging e ninguem repara.

select q.id_compra, q.id_item_compra
from {{ ref('quarentena_precos') }} q
join {{ ref('mart_precos') }} m
    on q.id_compra = m.id_compra
   and q.id_item_compra = m.id_item_compra
