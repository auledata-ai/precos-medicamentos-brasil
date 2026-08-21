"""Contrato com a fonte. Bate na API real.

Falha aqui não é bug nosso: é mudança de contrato da fonte, e precisa de ser
distinguível de falha de lógica. Por isso corre em marcador próprio e fica
fora do hook de pre-commit.
"""

import pytest
from ingestao.cliente import Cliente
from ingestao.coleta import (
    CLASSE_MEDICAMENTOS,
    coletar_catalogo,
    coletar_precos,
    coletar_precos_por_pdm,
)

pytestmark = pytest.mark.contrato

# Campos de que a análise depende. Se um destes desaparecer, o estudo quebra.
CAMPOS_DE_PRECO = {
    "idCompra",
    "idItemCompra",
    "codigoItemCatalogo",
    "precoUnitario",
    "quantidade",
    "dataCompra",
    "codigoMunicipio",
    "estado",
    "esfera",
    "nomeUnidadeFornecimento",
    "capacidadeUnidadeFornecimento",
    "siglaUnidadeMedida",
    "nomeFornecedor",
}
CAMPOS_DE_CATALOGO = {"codigoItem", "codigoClasse", "descricaoItem", "codigoPdm"}


class TestContratoDoCatalogo:
    def test_a_classe_de_medicamentos_ainda_existe(self):
        registos = coletar_catalogo(Cliente())
        assert len(registos) > 1000, "catálogo encolheu de forma inesperada"
        assert all(r.payload["codigoClasse"] == CLASSE_MEDICAMENTOS for r in registos)

    def test_os_campos_do_catalogo_continuam_presentes(self):
        registo = coletar_catalogo(Cliente())[0]
        assert CAMPOS_DE_CATALOGO <= set(registo.payload)


class TestContratoDosPrecos:
    def test_os_campos_de_preco_continuam_presentes(self):
        registos = coletar_precos(Cliente(), 354314)
        assert registos, "item de referência deixou de ter compras registadas"
        assert CAMPOS_DE_PRECO <= set(registos[0].payload)

    def test_o_municipio_continua_em_codigo_ibge_de_sete_digitos(self):
        """A junção com dados do IBGE depende disto."""
        for r in coletar_precos(Cliente(), 354314):
            codigo = str(r.payload["codigoMunicipio"])
            assert len(codigo) == 7 and codigo.isdigit(), codigo


class TestContratoDoPdm:
    def test_a_consulta_por_pdm_contem_a_consulta_por_item(self):
        """O pipeline coleta por PDM em vez de por item, o que depende de o
        PDM devolver um superconjunto. Se a fonte mudar o agrupamento, a
        cobertura muda sem aviso e este teste apanha (ver ADR 0005)."""
        chave = lambda r: (str(r.payload["idCompra"]), str(r.payload["idItemCompra"]))  # noqa: E731
        por_item = {chave(r) for r in coletar_precos(Cliente(), 354314)}
        por_pdm = {chave(r) for r in coletar_precos_por_pdm(Cliente(), 348)}
        assert por_item, "item de referência deixou de ter compras"
        assert por_item <= por_pdm, f"{len(por_item - por_pdm)} registos fora do PDM"
