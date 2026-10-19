.DEFAULT_GOAL := shell

# Autodetect the container runtime (podman preferred, docker fallback).
CONTAINER_CMD ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)
CONTAINER_NAME = openglredbook9

# This Makefile lives at the repo root. The container mounts the whole repo at
# /openglredbook9 and builds BOTH halves there: the C examples (cmake -> example
# binaries in /opt/rb9-build/bin) and the Python port (a flat set of demos run
# by path, python/<NN-name>/<demo>.py). The C demos load assets by the
# cwd-relative path "media/..." from bin/; the Python port reads the same
# bin/media/ by walking up from python/ (no env var needed).
REPO_ROOT := $(CURDIR)
REPO_MOUNT := /openglredbook9
PKG_DIR := $(REPO_MOUNT)/python

# Extra flags for every container `run`. Auto-set when running nested inside a
# runClaudeInContainer/runCrushInContainer sandbox (which exports NESTED_PODMAN=1),
# so podman-in-podman works; empty on a normal host. On `run` lines only.
PODMAN_RUN_FLAGS ?= $(if $(filter 1,$(NESTED_PODMAN)),--cgroups=disabled)

TMUX_FILE := $(HOME)/.tmux.conf
TMUX_REAL_PATH := $(shell readlink -f $(TMUX_FILE))
TMUX_MOUNT := $(shell if [ -f $(TMUX_REAL_PATH) ]; then echo "-v $(TMUX_REAL_PATH):/root/.tmux.conf:Z" ; fi)

GITCONFIG_FILE := $(HOME)/.gitconfig
GITCONFIG_REAL_PATH := $(shell readlink -f $(GITCONFIG_FILE))
GITCONFIG_MOUNT := $(shell if [ -f $(GITCONFIG_REAL_PATH) ]; then echo "-v $(GITCONFIG_REAL_PATH):/root/.gitconfig:Z" ; fi)

# Mount the repo root (so the C sources, shaders and bin/media are reachable)
# plus the live entrypoint scripts over their in-image paths (so edits take
# effect without a rebuild). `--security-opt label=disable` instead of a :z/:Z
# relabel: the mounted tree includes the ~266 MB bin/media, expensive to relabel
# and shared with the host, so SELinux confinement is turned off for the (local,
# dev) container rather than relabel the repo.
FILES_TO_MOUNT = --security-opt label=disable \
                 -v $(REPO_ROOT):$(REPO_MOUNT) \
                 -v $(CURDIR)/entrypoint/entrypoint.sh:/entrypoint.sh \
                 -v $(CURDIR)/entrypoint/shell.sh:/usr/local/bin/shell.sh \
                 -v $(CURDIR)/entrypoint/loadpackages.sh:/usr/local/bin/loadpackages.sh \
                 $(TMUX_MOUNT) \
                 $(GITCONFIG_MOUNT)

USE_X = -e DISPLAY=$(DISPLAY) \
        -v /tmp/.X11-unix:/tmp/.X11-unix

WAYLAND_FLAGS_FOR_CONTAINER = -e "XDG_SESSION_TYPE=wayland" \
                              -e "WAYLAND_DISPLAY=${WAYLAND_DISPLAY}" \
                              -e "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}" \
                              -e "PYGLFW_LIBRARY=/usr/lib64/libglfw.so.3" \
                              -v "${XDG_RUNTIME_DIR}:${XDG_RUNTIME_DIR}"

# Configure + build the C examples against the live mount. The build tree is
# /opt/rb9-build, OUTSIDE the mount, so the host's own build/ and debugBuild/
# caches cannot collide with it; the image baked + configured it, so this is a
# fast incremental relink. CMake writes the binaries into /opt/rb9-build/bin.
C_BUILD_PRELUDE = cmake -S $(REPO_MOUNT) -B /opt/rb9-build -G Ninja \
	-DCMAKE_BUILD_TYPE=Release >/dev/null && cmake --build /opt/rb9-build


.PHONY: all
all: image ## Build the container image

.PHONY: image
image: ## Build the podman image (bakes + builds the C examples)
	$(CONTAINER_CMD) build \
                         -t $(CONTAINER_NAME) \
                         .

# `shell` forwards BOTH X11 and Wayland, so the container has both display
# backends. A Python demo (`cd python && run 01-triangles`) uses Wayland
# natively; a C demo must use X11 because gl3w resolves GL through GLX and
# cannot on an EGL/Wayland context -- so the shell provides a `run-c <dir>`
# helper that launches the C example with WAYLAND_DISPLAY unset (→ X11/XWayland).
.PHONY: shell
shell: ## Shell in an ephemeral container (repo root; both X11 + Wayland; run/run-c helpers)
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) -it --rm \
		--entrypoint /bin/bash \
		$(FILES_TO_MOUNT) \
		$(USE_X) \
		$(WAYLAND_FLAGS_FOR_CONTAINER) \
		$(CONTAINER_NAME) \
		/usr/local/bin/shell.sh

# run/list/run-c/build-c override the image ENTRYPOINT (the health check) with
# /bin/bash so the command after it runs -- same as `shell`.
.PHONY: run
run: ## Run a Python demo in the container: make run DEMO=01-triangles
	@if [ -z "$(DEMO)" ]; then echo "usage: make run DEMO=<demo, e.g. 01-triangles>"; exit 1; fi
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) -it --rm \
		--entrypoint /bin/bash \
		$(FILES_TO_MOUNT) \
		$(USE_X) \
		$(WAYLAND_FLAGS_FOR_CONTAINER) \
		$(CONTAINER_NAME) \
		-c '[ -f $(PKG_DIR)/$(DEMO).py ] || { echo "no such demo: $(DEMO)"; exit 1; }; \
		    source /venv/bin/activate && python $(PKG_DIR)/$(DEMO).py'

.PHONY: list
list: ## List the Python demos
	@ls $(REPO_ROOT)/python/*.py | xargs -n1 basename | sed 's/\.py$$//' | sort

.PHONY: check
check: ## Import every Python demo module (no display): make check
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) --rm \
		$(FILES_TO_MOUNT) \
		$(CONTAINER_NAME)

# Read-only type gate: ty (correctness) over the redbook9 package + every demo,
# plus tools/check_local_annotations.py (completeness -- the "annotate every
# binding" rule ty can't enforce). Editable-install first so `from redbook9
# import ...` resolves. Every step runs and the target fails if ANY failed
# (s=1 accumulates). `$$s`/`$$(...)` are literal `$` for the shell.
.PHONY: type-check
type-check: ## Type-check the Python port: ty + annotate-every-binding checker
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) --rm \
		--entrypoint /bin/bash \
		$(FILES_TO_MOUNT) \
		$(CONTAINER_NAME) \
		-c 'source /venv/bin/activate && cd $(PKG_DIR) && \
		    uv pip install --no-deps --no-index --no-build-isolation -e . \
		        --python "$$(which python)" >/dev/null; \
		    s=0; \
		    ty check redbook9 || s=1; \
		    ty check *.py || s=1; \
		    cd $(REPO_MOUNT) && \
		    python tools/check_local_annotations.py --include-module python || s=1; \
		    exit $$s'

.PHONY: format
format: ## Format the Python port (ruff check --fix + ruff format) in the container
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) --rm \
		--entrypoint /bin/bash \
		$(FILES_TO_MOUNT) \
		$(CONTAINER_NAME) \
		-c 'cd $(REPO_MOUNT) && bash entrypoint/format.sh'

.PHONY: build-c
build-c: ## Build the C examples in the container (into /opt/rb9-build/bin)
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) --rm \
		--entrypoint /bin/bash \
		$(FILES_TO_MOUNT) \
		$(CONTAINER_NAME) \
		-c "$(C_BUILD_PRELUDE)"

# run-c forwards both backends (like `shell`) but launches the C binary with
# WAYLAND_DISPLAY unset, so GLFW uses X11/GLX -- gl3w cannot resolve GL on an
# EGL/Wayland context, so a C demo under Wayland opens a window and then cannot
# draw. On a Wayland host X11 is XWayland, where GLX works. (The Python port
# uses PyOpenGL, which handles EGL, so `run` stays on Wayland.) The example
# loads media via the cwd-relative "media/..." path, so it runs from bin/.
.PHONY: run-c
run-c: ## Run a C example on your display: make run-c DEMO=01-triangles
	@if [ -z "$(DEMO)" ]; then echo "usage: make run-c DEMO=<example-dir, e.g. 01-triangles>"; exit 1; fi
	$(CONTAINER_CMD) run $(PODMAN_RUN_FLAGS) -it --rm \
		--entrypoint /bin/bash \
		$(FILES_TO_MOUNT) \
		$(USE_X) \
		$(WAYLAND_FLAGS_FOR_CONTAINER) \
		$(CONTAINER_NAME) \
		-c "$(C_BUILD_PRELUDE) && cd $(REPO_MOUNT)/bin && env -u WAYLAND_DISPLAY /opt/rb9-build/bin/$(DEMO)"

.PHONY: clean
clean: ## Remove C and Python build artefacts
	rm -rf build debugBuild debugBuildInstall python/**/__pycache__ python/.ruff_cache

.PHONY: image-export
image-export: ## Export the OCI image to a tarball
	$(CONTAINER_CMD) save $(CONTAINER_NAME) -o $(CONTAINER_NAME)-$(shell date +%m-%d-%Y_%H-%M-%S).tar

.PHONY: image-import
image-import: ## Import a tarball as the OCI image: make image-import FILE=foo.tar
	$(CONTAINER_CMD) load -i $(FILE)

.PHONY: help
help:
	@grep --extended-regexp '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
