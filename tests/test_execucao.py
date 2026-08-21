"""Orquestração da coleta. Cliente falso, Postgres real."""

import pytest
from ingestao.cliente import ErroDaFonte, FonteIndisponivel
from ingestao.execucao import coletar_lote, planear_lotes, sincronizar_catalogo
from ingestao.repositorio import cobertura, guardar_catalogo

from tests.test_repositorio import item

pytestmark = pytest.mark.postgres


class ClienteFalso:
    """Devolve respostas guionadas por código de item.

    Um valor que seja Exception é levantado, o que permite guionar falha de
    um item específico sem tocar na rede.
    """

    def __init__(self, por_codigo=None, catalogo=None):
        self.por_codigo = por_codigo or {}
        self.catalogo = catalogo or []
        self.chamadas = []

    def paginar(self, caminho, parametros, tamanho_pagina=500):
        self.chamadas.append((caminho, parametros))
        if "catalogo" in caminho.lower() or "Material" in caminho:
            if "codigo" not in parametros:
                return self.catalogo
        resposta = self.por_codigo.get(parametros.get("codigo"), [])
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def preco_bruto(id_compra, id_item, codigo_item=1):
    return {
        "idCompra": id_compra,
        "idItemCompra": id_item,
        "precoUnitario": 1.0,
        "codigoItemCatalogo": codigo_item,
    }


class TestSincronizarCatalogo:
    def test_guarda_os_itens_e_cria_o_controle(self, conexao):
        cliente = ClienteFalso(
            catalogo=[
                {"codigoItem": 1, "codigoClasse": 6505, "descricaoItem": "A", "codigoPdm": 1},
                {"codigoItem": 2, "codigoClasse": 6505, "descricaoItem": "B", "codigoPdm": 2},
            ]
        )
        assert sincronizar_catalogo(cliente, conexao) == 2
        assert cobertura(conexao).total == 2


class TestPlanearLotes:
    def test_distribui_em_rodizio_e_nao_em_blocos(self, conexao):
        """Códigos próximos têm volumes parecidos. Em blocos contíguos, um
        lote apanharia todos os itens pesados e seria o único a demorar."""
        guardar_catalogo(conexao, [item(n) for n in range(1, 7)])
        lotes = planear_lotes(conexao, n_lotes=3)
        assert [len(x) for x in lotes] == [2, 2, 2]
        # rodizio: o primeiro lote leva o 1 e o 4, nao o 1 e o 2
        assert lotes[0] != sorted(lotes[0])[:2] or "4" in lotes[0]

    def test_nao_devolve_lotes_vazios(self, conexao):
        guardar_catalogo(conexao, [item(1)])
        assert planear_lotes(conexao, n_lotes=8) == [["1"]]

    def test_sem_pendentes_devolve_lista_vazia(self, conexao):
        assert planear_lotes(conexao, n_lotes=4) == []

    def test_rejeita_numero_de_lotes_invalido(self, conexao):
        with pytest.raises(ValueError, match="n_lotes"):
            planear_lotes(conexao, n_lotes=0)


class TestColetarLote:
    def test_conta_com_compras_e_sem_compras(self, conexao):
        guardar_catalogo(conexao, [item(1), item(2)])
        cliente = ClienteFalso({"1": [preco_bruto("C1", "I1")], "2": []})
        r = coletar_lote(cliente, conexao, ["1", "2"])
        assert (r.sucesso, r.sem_compras, r.falha, r.registros) == (1, 1, 0, 1)

    def test_falha_de_um_item_nao_derruba_o_lote(self, conexao):
        """É o requisito central: milhares de chamadas, alguma falha sempre.
        Rebentar desperdiçaria os itens já processados."""
        guardar_catalogo(conexao, [item(n) for n in (1, 2, 3)])
        cliente = ClienteFalso(
            {
                "1": [preco_bruto("C1", "I1")],
                "2": FonteIndisponivel("503 repetido"),
                "3": [preco_bruto("C3", "I1")],
            }
        )
        r = coletar_lote(cliente, conexao, ["1", "2", "3"])
        assert (r.sucesso, r.falha) == (2, 1)
        c = cobertura(conexao)
        assert (c.sucesso, c.falha) == (2, 1)

    def test_erro_do_pedido_tambem_e_isolado(self, conexao):
        guardar_catalogo(conexao, [item(1), item(2)])
        cliente = ClienteFalso({"1": ErroDaFonte("400"), "2": [preco_bruto("C", "I")]})
        assert coletar_lote(cliente, conexao, ["1", "2"]).falha == 1

    def test_progresso_persiste_apesar_da_falha_seguinte(self, conexao):
        """Commit por item: o que foi coletado antes da falha fica gravado."""
        guardar_catalogo(conexao, [item(1), item(2)])
        cliente = ClienteFalso(
            {
                "1": [preco_bruto("C1", "I1")],
                "2": FonteIndisponivel("caiu"),
            }
        )
        coletar_lote(cliente, conexao, ["1", "2"])
        assert conexao.execute("select count(*) c from raw.precos").fetchone()["c"] == 1

    def test_reexecutar_o_lote_nao_duplica(self, conexao):
        guardar_catalogo(conexao, [item(1)])
        cliente = ClienteFalso({"1": [preco_bruto("C1", "I1")]})
        coletar_lote(cliente, conexao, ["1"])
        coletar_lote(cliente, conexao, ["1"])
        assert conexao.execute("select count(*) c from raw.precos").fetchone()["c"] == 1

    def test_lote_vazio_nao_rebenta(self, conexao):
        assert coletar_lote(ClienteFalso(), conexao, []).pdms == 0
