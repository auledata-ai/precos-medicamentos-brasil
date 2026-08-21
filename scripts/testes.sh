#!/usr/bin/env bash
#
# Corre a suite completa, incluindo o que precisa de infra.
#
#   ./scripts/testes.sh            rapidos + postgres
#   ./scripts/testes.sh --tudo     acrescenta o contrato com a fonte real
#
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; . ./.env; set +a
export POSTGRES_DSN="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5433/${POSTGRES_DB}"

uv run ruff check
if [ "${1:-}" = "--tudo" ]; then
  uv run pytest -q
else
  # O contrato bate na API real e demora quase um minuto. Fica de fora por
  # omissao para a suite continuar a ser corrida com frequencia.
  uv run pytest -q -m "not contrato"
fi
