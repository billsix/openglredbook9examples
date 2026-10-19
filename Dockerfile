FROM registry.fedoraproject.org/fedora:44

COPY entrypoint/*.sh /usr/local/bin/
COPY entrypoint/entrypoint.sh /
COPY python/requirements.txt /requirements.txt

RUN  --mount=type=cache,target=/var/cache/libdnf5 \
     --mount=type=cache,target=/var/lib/dnf \
     echo "keepcache=True" >> /etc/dnf/dnf.conf && \
     dnf upgrade -y && \
     dnf install -y \
                   gcc \
                   gcc-c++ \
                   make \
                   cmake \
                   ninja-build \
                   git \
                   glfw \
                   glfw-devel \
                   python3-glfw \
                   python3-numpy \
                   python3-pillow \
                   python3-pyopengl \
                   python3-pytest \
                   python3-virtualenv \
                   ruff \
                   uv \
                   tmux \
                   which \
                   libglvnd-gles \
                   libXcomposite \
                   libXcursor \
                   libXdamage \
                   libXfixes \
                   libXft \
                   libXi \
                   libXinerama \
                   libXmu \
                   libXrandr \
                   libXrender \
                   libXtst \
                   libXxf86vm \
                   mesa-dri-drivers \
                   mesa-libGLU-devel \
                   libwayland-client \
                   libwayland-cursor \
                   libwayland-egl \
                   libxkbcommon \
                   libdecor \
                   mesa-libGL-devel \
                   mesa-libEGL-devel \
                   libX11-devel \
                   libXrandr-devel \
                   libXi-devel \
                   libXcursor-devel \
                   libXinerama-devel \
                   wayland-devel \
                   wayland-protocols-devel \
                   libxkbcommon-devel \
                   extra-cmake-modules ; \
    python3 -m venv --system-site-packages /venv/ && \
    export VIRTUAL_ENV_DISABLE_PROMPT=1 && \
    source /venv/bin/activate && \
    dnf install -y libatomic && \
    uv pip install setuptools ty && \
    uv pip install --python "$(which python)" -r /requirements.txt && \
    rm /requirements.txt

# Bake the C examples from the source so a built image is validated at build
# time and a pulled image is runnable standalone. `make shell` bind-mounts the
# live repo over /openglredbook9, which SHADOWS this baked copy; the entrypoint
# then re-builds the C (incremental) against the live mount so the binaries
# always match the mounted source. The Python port's shared `redbook9` package
# is editable-installed (-e) so the demo scripts import it (`from redbook9
# import ...`) with no sys.path hacks; demos still run by path (python
# <NN-name>.py) and read media from the sibling bin/media/.
#
# The build TREE lives at /opt/rb9-build, OUTSIDE the /openglredbook9 mount, on
# purpose: `make shell` bind-mounts the host repo over /openglredbook9, and the
# host's own build/ and debugBuild/ (CMakeCaches configured for the host path)
# would otherwise collide with a build tree under the mount and cmake would
# refuse ("source does not match"). CMake writes the example binaries into
# <build>/bin; the C examples load assets by the cwd-relative path "media/...",
# so they are launched with cwd set to the repo's bin/ (where bin/media/ lives).
COPY . /openglredbook9
RUN cmake -S /openglredbook9 -B /opt/rb9-build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release && \
    cmake --build /opt/rb9-build && \
    export VIRTUAL_ENV_DISABLE_PROMPT=1 && \
    source /venv/bin/activate && \
    cd /openglredbook9/python && \
    uv pip install --no-deps --no-index --no-build-isolation -e . \
        --python "$(which python)"

ENTRYPOINT ["/entrypoint.sh"]
