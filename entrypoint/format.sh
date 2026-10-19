#!/bin/env bash
# Format the Python port: ruff check --fix + ruff format over python/ (the
# shared package + the demo scripts). Run this after completing a unit of work,
# before staging, so the staged code is formatted.
#
# Portable: activates the container venv when present, else uses the caller's
# env; every path is relative to the repo root, so it runs identically in the
# container (cd /<repo>) and on the host (cd <repo>). ruff is on PATH (dnf), so
# the venv is not required.
#
# Fail-on-any-step: every step runs (one pass reports all the red) and the
# script exits nonzero if ANY step failed.
export VIRTUAL_ENV_DISABLE_PROMPT=1
[ -f /venv/bin/activate ] && source /venv/bin/activate

status=0
run() { "$@" || status=1; }

run ruff check python --fix
run ruff format python

exit $status
