#!/bin/bash
set -e

npm install --prefer-offline --no-audit --no-fund 2>/dev/null || true

npm run build:css

pip install -q -r requirements.txt 2>/dev/null || true
