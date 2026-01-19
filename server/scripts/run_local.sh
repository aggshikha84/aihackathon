#!/usr/bin/env bash
set -e

export $(grep -v '^#' .env | xargs)

python -m app.main
