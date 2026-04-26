#!/bin/bash
set -e
cd "$(dirname "$0")" || exit 1

# Thin launcher: delegate to the unified stack runner.
exec bash ./start_all.sh
