"""Testes do cliente HTTP. Nenhum toca na rede."""

import time

import pytest
import responses
from ingestao.cliente import (
    BASE,
    Cliente,
    ErroDaFonte,
    FonteIndisponivel,
    Politica,
)

CAMINHO = "/modulo-material/4_consultarItemMaterial"
URL = f"{BASE}{CAMINHO}"


@pytest.fixture
def rapido():
    """Política sem esperas, para o teste não demorar o que a produção demora."""
    return Politica(espera_inicial=0, espera_maxima=0, intervalo_minimo=0, tentativas=3)


class TestRepeticao:
    @responses.activate
    def test_devolve_o_corpo_quando_a_fonte_responde(self, rapido):
        responses.add(responses.GET, URL, json={"resultado": [{"a": 1}]}, status=200)
        assert Cliente(rapido).obter(CAMINHO, {}) == {"resultado": [{"a": 1}]}

    @responses.activate
    def test_repete_em_erro_transitorio_e_acaba_por_conseguir(self, rapido):
        responses.add(responses.GET, URL, status=503)
        responses.add(responses.GET, URL, status=500)
        responses.add(responses.GET, URL, json={"resultado": []}, status=200)
        assert Cliente(rapido).obter(CAMINHO, {}) == {"resultado": []}
        assert len(responses.calls) == 3

    @responses.activate
    def test_desiste_depois_do_limite_de_tentativas(self, rapido):
        responses.add(responses.GET, URL, status=503)
        with pytest.raises(FonteIndisponivel):
            Cliente(rapido).obter(CAMINHO, {})
        assert len(responses.calls) == rapido.tentativas

    @responses.activate
    def test_nao_repete_erro_nosso(self, rapido):
        """400 e defeito no pedido. Repetir esconde o defeito e gasta a fonte."""
        responses.add(responses.GET, URL, status=400, body="parametro invalido")
        with pytest.raises(ErroDaFonte, match="400"):
            Cliente(rapido).obter(CAMINHO, {})
        assert len(responses.calls) == 1

    @responses.activate
    def test_429_e_tratado_como_transitorio(self, rapido):
        """Limite de taxa pede espera, não desistência."""
        responses.add(responses.GET, URL, status=429)
        responses.add(responses.GET, URL, json={"resultado": []}, status=200)
        Cliente(rapido).obter(CAMINHO, {})
        assert len(responses.calls) == 2


class TestLimiteDeTaxa:
    @responses.activate
    def test_respeita_o_intervalo_minimo_entre_chamadas(self):
        responses.add(responses.GET, URL, json={"resultado": []}, status=200)
        cliente = Cliente(Politica(intervalo_minimo=0.2))
        inicio = time.monotonic()
        for _ in range(3):
            cliente.obter(CAMINHO, {})
        # Tres chamadas, dois intervalos de 0,2s no minimo.
        assert time.monotonic() - inicio >= 0.4


class TestPaginacao:
    @responses.activate
    def test_para_quando_a_pagina_vem_incompleta(self, rapido):
        responses.add(responses.GET, URL, json={"resultado": [{"i": n} for n in range(10)]})
        responses.add(responses.GET, URL, json={"resultado": [{"i": 10}]})
        obtido = Cliente(rapido).paginar(CAMINHO, {}, tamanho_pagina=10)
        assert len(obtido) == 11
        assert len(responses.calls) == 2

    @responses.activate
    def test_pagina_vazia_encerra(self, rapido):
        responses.add(responses.GET, URL, json={"resultado": []})
        assert Cliente(rapido).paginar(CAMINHO, {}, tamanho_pagina=10) == []

    @responses.activate
    def test_resultado_ausente_nao_rebenta(self, rapido):
        """A fonte já devolveu corpo sem a chave 'resultado'."""
        responses.add(responses.GET, URL, json={})
        assert Cliente(rapido).paginar(CAMINHO, {}, tamanho_pagina=10) == []

    @pytest.mark.parametrize("tamanho", [0, 9, 501, 1000])
    def test_rejeita_tamanho_de_pagina_fora_do_intervalo(self, rapido, tamanho):
        """Abaixo de 500 a API ignora o filtro de classe em silêncio, e fora
        do intervalo devolve 400. Falhar aqui é melhor que descobrir depois."""
        with pytest.raises(ValueError, match="tamanhoPagina"):
            Cliente(rapido).paginar(CAMINHO, {}, tamanho_pagina=tamanho)
