-- A chave natural da fonte tem de continuar unica depois do anti-join com a
-- quarentena. Um duplicado aqui multiplicaria registros nas medianas sem dar
-- qualquer sinal.

select id_compra, id_item_compra, count(*) as n
from {{ ref('mart_precos') }}
group by id_compra, id_item_compra
having count(*) > 1
