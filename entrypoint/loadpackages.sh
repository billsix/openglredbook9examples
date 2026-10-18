#!/bin/env bash
# Prepare the mounted repo: build the C examples (incremental). Called by
# shell.sh on `make shell`. No `set -e`, so a C build failure still lets the
# shell open (the errors print; you debug inside). Also editable-installs the
# Python port's `redbook9` package so demos import it.

export VIRTUAL_ENV_DISABLE_PROMPT=1
source /venv/bin/activate

# Build the C examples. The build tree /opt/rb9-build is OUTSIDE the mount: the
# baked image already configured + built it, so this is a fast incremental
# relink against the live source. A build tree under /openglredbook9 would
# collide with the host's own build/ and debugBuild/ caches (configured for the
# host path) and cmake would refuse. CMake writes binaries into /opt/rb9-build/bin.
cmake -S /openglredbook9 -B /opt/rb9-build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build /opt/rb9-build

# Editable-install the shared `redbook9` package (deps pre-installed in image).
( cd /openglredbook9/python && \
  uv pip install --no-deps --no-index --no-build-isolation -e . \
      --python "$(which python)" )
