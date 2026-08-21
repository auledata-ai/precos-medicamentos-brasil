"""Persistência e semântica de retomada. Precisam do Postgres do compose."""

from datetime import UTC, datetime, timedelta

import pytest
from ingestao.coleta import RegistoBruto
from ingestao.repositorio import (
    cobertura,
    guardar_catalogo,
    guardar_precos,
    itens_pendentes,
    marcar_coletado,
    marcar_falha,
)

pytestmark = pytest.mark.postgres


def item(codigo: int, descricao: str = "MEDICAMENTO X") -> RegistoBruto:
    return RegistoBruto.de(
        "/catalogo", {}, {"codigoItem": codigo, "codigoClasse": 6505,
                          "descricaoItem": descricao}
    )


def preco(id_compra: str, id_item: str, valor: float = 1.0) -> RegistoBruto:
    return RegistoBruto.de(
        "/precos", {}, {"idCompra": id_compra, "idItemCompra": id_item,
                        "precoUnitario": valor}
    )


class TestIdempotencia:
    def test_guardar_o_mesmo_catalogo_duas_vezes_nao_duplica(self, conexao):
        guardar_catalogo(conexao, [item(1), item(2)])
        guardar_catalogo(conexao, [item(1), item(2)])
        assert conexao.execute("select count(*) c from raw.catalogo").fetchone()["c"] == 2

    def test_recoleta_atualiza_o_payload(self, conexao):
        guardar_catalogo(conexao, [item(1, "NOME ANTIGO")])
        guardar_catalogo(conexao, [item(1, "NOME NOVO")])
        linha = conexao.execute("select payload from raw.catalogo").fetchone()
        assert linha["payload"]["descricaoItem"] == "NOME NOVO"

    def test_precos_repetidos_nao_duplicam(self, conexao):
        """A chave natural é (idCompra, idItemCompra)."""
        guardar_catalogo(conexao, [item(1)])
        guardar_precos(conexao, "1", [preco("C1", "I1"), preco("C1", "I2")])
        guardar_precos(conexao, "1", [preco("C1", "I1"), preco("C1", "I2")])
        assert conexao.execute("select count(*) c from raw.precos").fetchone()["c"] == 2

    def test_recoletar_catalogo_nao_rebaixa_item_ja_coletado(self, conexao):
        """Ler o catálogo de novo não pode apagar o progresso da coleta."""
        guardar_catalogo(conexao, [item(1)])
        marcar_coletado(conexao, "1", registos_obtidos=5)
        guardar_catalogo(conexao, [item(1)])
        estado = conexao.execute(
            "select estado from raw.controlo_ingestao").fetchone()["estado"]
        assert estado == "sucesso"


class TestEstadoDaColeta:
    def test_zero_registos_e_sem_compras_e_nao_falha(self, conexao):
        """Metade do catálogo não tem compra. Tratar como erro faria o
        pipeline repetir eternamente itens que nunca terão dados."""
        guardar_catalogo(conexao, [item(1)])
        marcar_coletado(conexao, "1", registos_obtidos=0)
        assert conexao.execute(
            "select estado from raw.controlo_ingestao").fetchone()["estado"] == "sem_compras"

    def test_falha_nao_apaga_a_ultima_coleta_boa(self, conexao):
        guardar_catalogo(conexao, [item(1)])
        marcar_coletado(conexao, "1", registos_obtidos=3)
        marcar_falha(conexao, "1", "503 da fonte")
        linha = conexao.execute(
            "select coletado_em, estado, tentativas from raw.controlo_ingestao").fetchone()
        assert linha["coletado_em"] is not None
        assert linha["estado"] == "falha"
        assert linha["tentativas"] == 1

    def test_falhas_sucessivas_incrementam(self, conexao):
        guardar_catalogo(conexao, [item(1)])
        marcar_falha(conexao, "1", "erro")
        marcar_falha(conexao, "1", "erro")
        assert conexao.execute(
            "select tentativas t from raw.controlo_ingestao").fetchone()["t"] == 2


class TestRetomada:
    def test_item_nunca_coletado_esta_pendente(self, conexao):
        guardar_catalogo(conexao, [item(1), item(2)])
        assert set(itens_pendentes(conexao)) == {"1", "2"}

    def test_item_coletado_agora_sai_da_fila(self, conexao):
        guardar_catalogo(conexao, [item(1), item(2)])
        marcar_coletado(conexao, "1", 5)
        assert itens_pendentes(conexao) == ["2"]

    def test_coleta_antiga_volta_a_ficar_pendente(self, conexao):
        """A fonte atualiza continuamente. Sem validade, o estudo congelaria
        no dia da primeira execução."""
        guardar_catalogo(conexao, [item(1)])
        conexao.execute(
            "update raw.controlo_ingestao set coletado_em = %s, estado = 'sucesso'",
            (datetime.now(UTC) - timedelta(days=30),),
        )
        assert itens_pendentes(conexao, validade=timedelta(days=7)) == ["1"]
        assert itens_pendentes(conexao, validade=timedelta(days=60)) == []

    def test_item_que_falha_sempre_sai_da_fila(self, conexao):
        """Sem teto de tentativas, um item que a fonte nunca serve seria
        repetido em todas as execuções, para sempre."""
        guardar_catalogo(conexao, [item(1)])
        for _ in range(3):
            marcar_falha(conexao, "1", "erro")
        assert itens_pendentes(conexao, max_tentativas=3) == []
        assert itens_pendentes(conexao, max_tentativas=99) == ["1"]

    def test_forcar_devolve_tudo(self, conexao):
        guardar_catalogo(conexao, [item(1), item(2)])
        marcar_coletado(conexao, "1", 5)
        marcar_coletado(conexao, "2", 0)
        assert set(itens_pendentes(conexao, forcar=True)) == {"1", "2"}

    def test_limite_recorta_a_fila(self, conexao):
        guardar_catalogo(conexao, [item(n) for n in range(1, 6)])
        assert len(itens_pendentes(conexao, limite=2)) == 2

    def test_nunca_coletados_vem_primeiro(self, conexao):
        """Numa execução limitada, prioriza quem nunca teve dado nenhum."""
        guardar_catalogo(conexao, [item(1), item(2)])
        conexao.execute(
            "update raw.controlo_ingestao set coletado_em = %s where codigo_item = '1'",
            (datetime.now(UTC) - timedelta(days=30),),
        )
        assert itens_pendentes(conexao, limite=1) == ["2"]


class TestCobertura:
    def test_conta_cada_estado(self, conexao):
        guardar_catalogo(conexao, [item(n) for n in range(1, 5)])
        marcar_coletado(conexao, "1", 10)
        marcar_coletado(conexao, "2", 0)
        marcar_falha(conexao, "3", "erro")
        c = cobertura(conexao)
        assert (c.total, c.sucesso, c.sem_compras, c.falha, c.pendente) == (4, 1, 1, 1, 1)
        assert c.registos == 10
