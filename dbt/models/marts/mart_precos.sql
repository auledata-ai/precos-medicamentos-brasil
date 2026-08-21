-- Base limpa da analise: o staging menos o que a quarentena excluiu.
--
-- O anti-join e contra a chave natural da fonte, nao contra uma linha
-- reconstruida. Se a quarentena crescer, esta tabela encolhe sozinha.

select p.*
from {{ ref('stg_precos') }} p
left join {{ ref('quarentena_precos') }} q
    on p.id_compra = q.id_compra
   and p.id_item_compra = q.id_item_compra
where q.id_compra is null
