"""Corre a análise e escreve os resultados em JSON.

    uv run python -m analise

O JSON é a fonte única dos números publicados: gráficos, posts e documentos
lêem daqui, e nenhum número é copiado à mão.
"""

import json
import os
import sys
from pathlib import Path

import psycopg

from analise.resultados import tudo

DESTINO = Path(__file__).resolve().parent.parent / "dados" / "resultados.json"


def _dsn() -> str:
    if dsn := os.environ.get("POSTGRES_DSN"):
        return dsn
    em_falta = [
        nome
        for nome in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
        if not os.environ.get(nome)
    ]
    if em_falta:
        raise SystemExit(f"faltam variáveis de ambiente: {', '.join(em_falta)}")
    servidor = os.environ.get("POSTGRES_HOST", "localhost")
    porta = os.environ.get("POSTGRES_PORT", "5433")
    return (
        f"postgresql://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@{servidor}:{porta}/"
        f"{os.environ['POSTGRES_DB']}"
    )


def main() -> int:
    with psycopg.connect(_dsn(), row_factory=psycopg.rows.dict_row) as ligacao:
        resultados = tudo(ligacao)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(resultados, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # T201: aqui o `print` e a interface do comando, nao depuracao. Quem
    # corre isto na linha de comandos precisa de saber onde o ficheiro foi
    # parar, e um logger escondia essa informacao atras de configuracao.
    print(f"escrito: {DESTINO}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
