"""Coleta do catálogo e dos preços.

Estes módulos apenas recolhem. Nenhuma tipagem, normalização ou regra de
negócio acontece aqui: isso pertence à staging, onde o contexto é conhecido.
A camada raw guarda a resposta como veio, com metadados suficientes para
reconstituir de onde e quando ela veio.

São funções puras sobre um cliente injetado, portanto testáveis sem Airflow
e sem rede.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ingestao.cliente import PAGINA_MAXIMA, Cliente

CAMINHO_CATALOGO = "/modulo-material/4_consultarItemMaterial"
CAMINHO_PRECOS = "/modulo-pesquisa-preco/1_consultarMaterial"

# Drogas e Medicamentos, no catálogo de materiais do governo federal.
CLASSE_MEDICAMENTOS = 6505


@dataclass(frozen=True)
class RegistoBruto:
    """Uma linha da fonte, com a proveniência anexada.

    O `hash_payload` permite detetar se a fonte mudou o conteúdo de um
    registro entre coletas, sem ter de comparar campo a campo.
    """

    endpoint: str
    parametros: dict[str, Any]
    coletado_em: datetime
    payload: dict[str, Any]
    hash_payload: str

    @classmethod
    def de(cls, endpoint: str, parametros: dict, payload: dict) -> RegistoBruto:
        canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return cls(
            endpoint=endpoint,
            parametros=parametros,
            coletado_em=datetime.now(UTC),
            payload=payload,
            hash_payload=hashlib.sha256(canonico.encode()).hexdigest(),
        )


def coletar_catalogo(cliente: Cliente, classe: int = CLASSE_MEDICAMENTOS) -> list[RegistoBruto]:
    """Todos os itens de uma classe do catálogo.

    A API devolve itens de outras classes quando o tamanho de página não é o
    máximo. Filtramos de novo aqui em vez de confiar no filtro remoto: é
    barato, e a alternativa é publicar preços de gaze cirúrgica como se
    fossem de medicamento.
    """
    parametros = {"codigoClasse": classe}
    itens = cliente.paginar(CAMINHO_CATALOGO, parametros, tamanho_pagina=PAGINA_MAXIMA)
    return [
        RegistoBruto.de(CAMINHO_CATALOGO, parametros, item)
        for item in itens
        if item.get("codigoClasse") == classe
    ]


def coletar_precos_por_pdm(cliente: Cliente, codigo_pdm: int | str) -> list[RegistoBruto]:
    """Todos os preços registrados para um PDM.

    O PDM agrupa itens equivalentes, e a consulta devolve os preços de todos
    numa só chamada. É a unidade de coleta desde o ADR 0005.

    Boa parte dos PDMs não tem compra alguma, e a resposta vazia é
    informação: devolve lista vazia, e quem chama registra a cobertura.
    """
    parametros = {"tipo": "codigoPdm", "codigo": str(codigo_pdm)}
    registros = cliente.paginar(CAMINHO_PRECOS, parametros, tamanho_pagina=PAGINA_MAXIMA)
    return [RegistoBruto.de(CAMINHO_PRECOS, parametros, r) for r in registros]


def coletar_precos(cliente: Cliente, codigo_item: int | str) -> list[RegistoBruto]:
    """Preços de um item de catálogo específico.

    Mantido para os testes de contrato, que comparam a consulta por item com
    a consulta por PDM. Não é usado no pipeline.
    """
    parametros = {"tipo": "codigoItemCatalogo", "codigo": str(codigo_item)}
    registros = cliente.paginar(CAMINHO_PRECOS, parametros, tamanho_pagina=PAGINA_MAXIMA)
    return [RegistoBruto.de(CAMINHO_PRECOS, parametros, r) for r in registros]
