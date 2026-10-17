#!/usr/bin/env bash
set -e
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8102}" --reload
