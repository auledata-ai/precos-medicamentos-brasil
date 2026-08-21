-- Regressao para um defeito real, nao uma verificacao de rotina.
--
-- A primeira versao da chave era `codigo_item | unidade_fornecimento`, e
-- "FRASCO" nao e uma quantidade: um unico grupo continha frascos de 50 ML a
-- 2 L, e ate ML misturado com G. Isso fabricava dispersao onde havia apenas
-- tamanhos diferentes, em 781 dos 2.325 grupos com amostra util.
--
-- Se alguem voltar a simplificar a chave, este teste falha.

select
    grupo_comparavel,
    count(distinct capacidade_unidade::text || '|' || coalesce(unidade_medida, '')) as variantes
from {{ ref('mart_precos') }}
group by grupo_comparavel
having count(distinct capacidade_unidade::text || '|' || coalesce(unidade_medida, '')) > 1
