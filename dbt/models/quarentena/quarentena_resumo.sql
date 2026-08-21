-- Quanto perdemos e porque. Publicavel tal e qual: um estudo que nao diz
-- quanto do dado deitou fora nao permite julgar o resto.

with total as (
    select count(*)::numeric as registros from {{ ref('stg_precos') }}
),

por_motivo as (
    select unnest(motivos) as motivo, count(*) as registros
    from {{ ref('quarentena_precos') }}
    group by 1
)

select
    m.motivo,
    m.registros,
    round(100.0 * m.registros / t.registros, 4) as porcentagem_do_total
from por_motivo m
cross join total t
order by m.registros desc
