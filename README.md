OpenGL Red Book Example Code
============================

This is the example code for the OpenGL Programming Guide (Red Book), 9th Edition.
It is mostly an import of code from previous editions with minor updates
to match some of the descriptions in the latest edition of the book.
We will be adding more samples and updating existing ones over time.
Treat this as a live repository. Pull requests and issues are welcome.
Go forth and fork!

This fork also carries a **Python port** of the samples (`python/`) and a
container that builds and runs **both** halves. See "Container" and
"Python port" below.

Container (C + Python)
----------------------

One image builds the C examples and carries the Python port; `make shell`
drops you at the repo root with both display backends. From the repo root:

```bash
make image                    # build the image (compiles the C examples)
make run-c DEMO=01-triangles  # run a C example on your display (X11)
make run   DEMO=01-triangles  # run the Python port of it (Wayland)
make check                    # import every Python demo, no display
make type-check               # ty + annotate-every-binding checker (no display)
make format                   # ruff check --fix + ruff format the port
make list                     # list the demo directories
make shell                    # interactive shell; then: run-c <dir> / run <dir>
```

> The C examples use gl3w, which resolves GL through GLX, so they run on
> X11/XWayland (`run-c` unsets `WAYLAND_DISPLAY`); the Python port uses
> PyOpenGL (EGL-capable) and runs on Wayland. The C build tree lives at
> `/opt/rb9-build`, outside the mount, so the host's own `build/` cache
> never collides with it. Details: `AGENTS.md`.

Building
--------

We are using CMake as our build system. To build the samples, enter
the "build" subdirectory and enter "cmake -G "{your generator here}" .."
Project files or makefiles will be produced in the build subdirectory.
We have tested Unix makefiles ("Unix Makefiles") and Visual Studio project files.
Visual Studio 2013 ("Visual Studio 12") was used to develop most of the samples.
An update to add support for 2015 will land shortly. Code should compile, but the
templates for the project files are not in the repository at this time.
Other compilers and IDEs should work, but we haven't tested them.

Running
-------

After building, there will be a large collection of executables in the bin directory.
These are the example applications, which you can directly execute.

The media is now included with the git repository, and
the samples should compile and run out-of-the box. Of course, make sure your
OpenGL drivers are up to date and that your hardware is capable of running OpenGL 4.5.
That's what this book is about. Some systems don't support OpenGL 4.5 and will therefore
not run some of the samples. Trying to run such samples on a machine that doesn't have
OpenGL 4.5 support will fail. For example, if a platform were limited to, say OpenGL 4.1,
then the samples wouldn't work on that platform. Please don't file bugs about that either.
Error checking in these applications is minimal. If you don't have media files or if
your OpenGL drivers are out of date, they'll probably fail spectacularly.

Python port
-----------

`python/` holds a behaviour-faithful Python translation of all 33 samples
(PyOpenGL + GLFW + imgui_bundle). It is a flat set of scripts run by path
(`python 01-triangles/triangles.py`), not a pip package, and it reads the
media from this repo's own `bin/media/` rather than carrying a copy. See
`python/README.md` to run it, and `tasks/reference/python-port/` for the
port's cold-start knowledge (porting rules, the frameworks, the
Mesa/PyOpenGL traps, the fidelity audit vs the C++).