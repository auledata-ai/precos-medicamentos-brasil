-- Quanto perdemos e porque. Publicavel tal e qual: um estudo que nao diz
-- quanto do dado deitou fora nao permite julgar o resto.

with total as (
    select count(*)::numeric as registos from {{ ref('stg_precos') }}
),

por_motivo as (
    select unnest(motivos) as motivo, count(*) as registos
    from {{ ref('quarentena_precos') }}
    group by 1
)

select
    m.motivo,
    m.registos,
    round(100.0 * m.registos / t.registos, 4) as percentagem_do_total
from por_motivo m
cross join total t
order by m.registos desc
