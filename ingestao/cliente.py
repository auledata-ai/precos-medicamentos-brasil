"""Cliente HTTP da API do Compras.gov.br.

Toda a comunicação com a fonte passa por aqui. A regra existe por três
motivos concretos:

- **Limite de taxa.** São cerca de 6.600 chamadas contra um portal público
  gratuito. Disparar sem intervalo é abuso, e leva a bloqueio.
- **Recuo exponencial.** A fonte devolve 5xx sob carga. Repetir de imediato
  agrava o problema em vez de o resolver.
- **Testabilidade.** Com o IO isolado, a lógica de coleta testa-se sem rede.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE = "https://dadosabertos.compras.gov.br"

# A API rejeita tamanhoPagina fora deste intervalo, e abaixo do maximo ignora
# em silencio o filtro de classe. Ver docs/decisions e a especificacao.
PAGINA_MINIMA = 10
PAGINA_MAXIMA = 500


class ErroDaFonte(RuntimeError):
    """A fonte respondeu, mas com erro que não vale a pena repetir."""


class FonteIndisponivel(RuntimeError):
    """A fonte falhou de forma repetida. Distingue-se de erro nosso."""


@dataclass(frozen=True)
class Politica:
    """Parâmetros de resiliência. Sem valores mágicos espalhados no código."""

    tentativas: int = 4
    espera_inicial: float = 1.0
    espera_maxima: float = 30.0
    timeout: float = 120.0
    intervalo_minimo: float = 0.35  # ~3 chamadas por segundo, no maximo
    # 429 e 5xx sao transitorios. 4xx (exceto 429) e erro nosso e nao repete.
    codigos_repetiveis: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass
class Cliente:
    """Cliente com limite de taxa e recuo exponencial.

    Não é seguro para uso concorrente: o limitador guarda o instante da
    última chamada em estado próprio. Cada worker deve ter o seu.
    """

    politica: Politica = field(default_factory=Politica)
    sessao: requests.Session = field(default_factory=requests.Session)
    _ultima_chamada: float = field(default=0.0, init=False)

    def _aguardar_vez(self) -> None:
        decorrido = time.monotonic() - self._ultima_chamada
        if decorrido < self.politica.intervalo_minimo:
            time.sleep(self.politica.intervalo_minimo - decorrido)
        self._ultima_chamada = time.monotonic()

    def _espera_do_recuo(self, tentativa: int) -> float:
        """Recuo exponencial com jitter.

        O jitter evita que várias execuções que falharam ao mesmo tempo
        voltem todas em sincronia e derrubem a fonte de novo.
        """
        base = min(
            self.politica.espera_inicial * (2**tentativa), self.politica.espera_maxima
        )
        return base * (0.5 + random.random() / 2)  # noqa: S311 - jitter, nao cripto

    def obter(self, caminho: str, parametros: dict[str, Any]) -> dict:
        """GET com repetição. Devolve o JSON já decodificado."""
        url = f"{BASE}{caminho}"
        ultimo_erro: Exception | None = None

        for tentativa in range(self.politica.tentativas):
            self._aguardar_vez()
            try:
                resposta = self.sessao.get(
                    url, params=parametros, timeout=self.politica.timeout
                )
            except requests.RequestException as exc:
                ultimo_erro = exc
                logger.warning("falha de rede em %s: %s", caminho, exc)
            else:
                if resposta.status_code == 200:
                    return resposta.json()
                if resposta.status_code not in self.politica.codigos_repetiveis:
                    # 4xx nao transitorio: repetir nao ajuda e esconde o defeito.
                    raise ErroDaFonte(
                        f"{caminho} devolveu {resposta.status_code}: "
                        f"{resposta.text[:200]}"
                    )
                ultimo_erro = ErroDaFonte(f"{caminho} devolveu {resposta.status_code}")
                logger.warning(
                    "resposta %s em %s, tentativa %d",
                    resposta.status_code,
                    caminho,
                    tentativa + 1,
                )

            if tentativa < self.politica.tentativas - 1:
                time.sleep(self._espera_do_recuo(tentativa))

        raise FonteIndisponivel(
            f"{caminho} falhou em {self.politica.tentativas} tentativas"
        ) from ultimo_erro

    def paginar(
        self, caminho: str, parametros: dict[str, Any], tamanho_pagina: int = PAGINA_MAXIMA
    ) -> list[dict]:
        """Percorre todas as páginas e devolve os resultados concatenados.

        Para quando uma página vem incompleta, que é o sinal de fim desta API.
        """
        if not PAGINA_MINIMA <= tamanho_pagina <= PAGINA_MAXIMA:
            raise ValueError(
                f"tamanhoPagina deve estar entre {PAGINA_MINIMA} e {PAGINA_MAXIMA}, "
                f"recebido {tamanho_pagina}"
            )
        recolhido: list[dict] = []
        pagina = 1
        while True:
            corpo = self.obter(
                caminho, {**parametros, "pagina": pagina, "tamanhoPagina": tamanho_pagina}
            )
            resultado = corpo.get("resultado") or []
            recolhido.extend(resultado)
            if len(resultado) < tamanho_pagina:
                return recolhido
            pagina += 1
