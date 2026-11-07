#!/bin/sh
# Fetch immutable, checksum-verified inputs. Works from any working directory.
set -eu
exec python3 "$(dirname "$0")/fetch_sources.py" "$@"
