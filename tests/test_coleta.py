"""Testes da coleta. Nenhum toca na rede."""

import responses
from ingestao.cliente import BASE, Cliente, Politica
from ingestao.coleta import (
    CAMINHO_CATALOGO,
    CAMINHO_PRECOS,
    CLASSE_MEDICAMENTOS,
    RegistoBruto,
    coletar_catalogo,
    coletar_precos,
)

RAPIDO = Politica(espera_inicial=0, espera_maxima=0, intervalo_minimo=0, tentativas=2)


class TestRegistoBruto:
    def test_guarda_a_proveniencia(self):
        r = RegistoBruto.de("/x", {"a": 1}, {"campo": "valor"})
        assert r.endpoint == "/x"
        assert r.parametros == {"a": 1}
        assert r.payload == {"campo": "valor"}
        assert r.coletado_em.tzinfo is not None

    def test_hash_e_estavel_independente_da_ordem_das_chaves(self):
        """A fonte não garante ordem. Sem canonicalização, o mesmo conteúdo
        produziria hashes diferentes e toda coleta pareceria alterada."""
        a = RegistoBruto.de("/x", {}, {"um": 1, "dois": 2})
        b = RegistoBruto.de("/x", {}, {"dois": 2, "um": 1})
        assert a.hash_payload == b.hash_payload

    def test_hash_muda_quando_o_conteudo_muda(self):
        a = RegistoBruto.de("/x", {}, {"preco": 1.0})
        b = RegistoBruto.de("/x", {}, {"preco": 2.0})
        assert a.hash_payload != b.hash_payload


class TestColetarCatalogo:
    @responses.activate
    def test_devolve_os_itens_da_classe(self, catalogo_real):
        responses.add(responses.GET, f"{BASE}{CAMINHO_CATALOGO}", json=catalogo_real)
        obtido = coletar_catalogo(Cliente(RAPIDO))
        assert len(obtido) == len(catalogo_real["resultado"])
        assert all(r.payload["codigoClasse"] == CLASSE_MEDICAMENTOS for r in obtido)

    @responses.activate
    def test_descarta_itens_de_outra_classe(self, catalogo_real):
        """A API já devolveu itens de outras classes quando o tamanho de
        página não era o máximo. Confiar no filtro remoto publicaria preço de
        material cirúrgico como se fosse medicamento."""
        contaminado = {
            "resultado": [
                *catalogo_real["resultado"],
                {"codigoItem": 999, "codigoClasse": 6510, "descricaoItem": "GAZE"},
            ]
        }
        responses.add(responses.GET, f"{BASE}{CAMINHO_CATALOGO}", json=contaminado)
        obtido = coletar_catalogo(Cliente(RAPIDO))
        assert all(r.payload["codigoClasse"] == CLASSE_MEDICAMENTOS for r in obtido)
        assert 999 not in {r.payload["codigoItem"] for r in obtido}


class TestColetarPrecos:
    @responses.activate
    def test_devolve_todos_os_registos(self, precos_reais):
        responses.add(responses.GET, f"{BASE}{CAMINHO_PRECOS}", json=precos_reais)
        obtido = coletar_precos(Cliente(RAPIDO), 354314)
        assert len(obtido) == len(precos_reais["resultado"])

    @responses.activate
    def test_preserva_o_payload_sem_transformar(self, precos_reais):
        """A camada raw não tipa nem normaliza. Se transformasse aqui,
        perderíamos a capacidade de distinguir erro nosso de erro da fonte."""
        responses.add(responses.GET, f"{BASE}{CAMINHO_PRECOS}", json=precos_reais)
        obtido = coletar_precos(Cliente(RAPIDO), 354314)
        assert obtido[0].payload == precos_reais["resultado"][0]

    @responses.activate
    def test_item_sem_compra_devolve_vazio(self):
        """Metade do catálogo não tem compra. Ausência é informação, não erro."""
        responses.add(responses.GET, f"{BASE}{CAMINHO_PRECOS}", json={"resultado": []})
        assert coletar_precos(Cliente(RAPIDO), 1) == []

    @responses.activate
    def test_passa_o_codigo_como_texto(self, precos_reais):
        """A API rejeita o parâmetro quando não é string."""
        responses.add(responses.GET, f"{BASE}{CAMINHO_PRECOS}", json=precos_reais)
        coletar_precos(Cliente(RAPIDO), 354314)
        assert "codigo=354314" in responses.calls[0].request.url
