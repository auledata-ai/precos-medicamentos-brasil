-- Esquema da camada raw e do controle de ingestao.
--
-- raw guarda a resposta como veio, em jsonb, com a proveniencia ao lado.
-- Tipagem e normalizacao pertencem a staging: se tipassemos aqui, um erro
-- nosso de conversao ficaria indistinguivel de um erro da fonte.

create schema if not exists raw;

create table if not exists raw.catalogo (
    codigo_item    text        primary key,
    payload        jsonb       not null,
    hash_payload   text        not null,
    endpoint       text        not null,
    parametros     jsonb       not null,
    coletado_em    timestamptz not null
);

create table if not exists raw.precos (
    -- Chave natural da fonte. Um item de compra e unico por (compra, item).
    id_compra       text        not null,
    id_item_compra  text        not null,
    codigo_item     text        not null,
    payload         jsonb       not null,
    hash_payload    text        not null,
    endpoint        text        not null,
    parametros      jsonb       not null,
    coletado_em     timestamptz not null,
    primary key (id_compra, id_item_compra)
);

create index if not exists precos_por_item on raw.precos (codigo_item);

-- Controle proprio, deliberadamente separado do estado do Airflow.
-- O Airflow sabe se uma task correu; isto sabe se um PDM foi coletado.
--
-- A unidade e o PDM e nao o item: um PDM agrupa itens equivalentes, e a
-- consulta por PDM devolve os precos de todos eles numa chamada. Sao 1.878
-- PDMs contra 12.359 itens (ver ADR 0005).
create table if not exists raw.controle_ingestao (
    codigo_pdm        text        primary key,
    coletado_em       timestamptz,
    registros_obtidos  integer     not null default 0,
    estado            text        not null default 'pendente'
        check (estado in ('pendente', 'sucesso', 'sem_compras', 'falha')),
    erro              text,
    tentativas        integer     not null default 0,
    atualizado_em     timestamptz not null default now()
);

-- A consulta de pendentes filtra por estado e validade, e ambos entram no indice.
create index if not exists controle_por_estado
    on raw.controle_ingestao (estado, coletado_em);
