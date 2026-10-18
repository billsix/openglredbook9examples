# Add an ASan + UBSan(trap) build gate

**Status:** proposed — needs go-ahead
**Created:** 2026-06-16

## Goal

Mirror the sanitizer gate the sibling **spimulator** project just gained: build
this code under **UBSan trap mode** (`-fsanitize=undefined
-fsanitize-trap=undefined` — any undefined behavior aborts with SIGILL, the
pass/fail gate) and under **AddressSanitizer** (`-fsanitize=address` — buffer
overflows, use-after-free, etc.), exercise something under each, and **fail the
build on any UB or memory error**. For C++, UBSan additionally checks `vptr`
(bad virtual dispatch / wrong-type downcast) and array bounds.

Primer on what ASan/UBSan are, why trap mode is the reliable gate (diagnostic
UBSan *under-reports*), and the integer-UB patterns to expect:
`/billopt/spimulator/tasks/archive/2026/06/16/ubsan-sweep.md`. How spimulator
wired it in (a `RUN_SANITIZERS` arg in the Dockerfile that does a second
instrumented build + test run, gated by the Makefile): search `RUN_SANITIZERS`
in `/billopt/spimulator/Dockerfile` and `/billopt/spimulator/Makefile`.

## What this project is (relevant constraints)

- **OpenGL Programming Guide ("Red Book"), 9th ed.** sample code (project
  `vermilion9`). **CMake** (`CMakeLists.txt`, `cmake_minimum_required(3.20)`,
  C++11 / C99). No Meson, **no Dockerfile/Makefile container template, no
  `CLAUDE.md`** — a bare upstream-style tree.
- Layout: a static **`vermilion`** support lib (`lib/`: `gl3w.c`,
  `LoadShaders`, `targa`, `vdds`, `loadtexture`, `vermilion`, `vbm`) plus
  ~35 example executables, one per `src/NN-<name>/<name>.cpp`.
- The CMake already **quiets upstream warnings** on `vermilion`
  (`-Wno-deprecated-declarations -Wno-narrowing -Wno-write-strings`) — a tell
  that even the "first-party" support lib is imported sample code.
- **glfw** is a system package if present, else **fetched via FetchContent**
  (glfw 3.4) at configure time — that fetched glfw is third-party and **must not
  be the gate's target**.
- **No test suite** (no `enable_testing`/`add_test`/ctest).
- Examples are **interactive GLFW windows** requiring **OpenGL 4.5**; per the
  README "error checking is minimal" and they "fail spectacularly" without media
  / a 4.5 driver. They run a render loop until closed.

## How to add the flags (CMake)

CMake has no `-Db_sanitize` equivalent; inject the flags yourself and scope them
to **`vermilion` + the example targets only**, never the fetched glfw:

```cmake
option(ENABLE_SANITIZERS "Build sample code under ASan/UBSan" OFF)
add_library(rb9_sanitizers INTERFACE)
if(ENABLE_SANITIZERS)
  target_compile_options(rb9_sanitizers INTERFACE
    -fsanitize=address,undefined -fsanitize-trap=undefined
    -fno-omit-frame-pointer -g)
  target_link_options(rb9_sanitizers INTERFACE
    -fsanitize=address,undefined -fsanitize-trap=undefined)
endif()
# target_link_libraries(vermilion PRIVATE rb9_sanitizers)
# in the example foreach: target_link_libraries(${EXAMPLE} PRIVATE rb9_sanitizers)
```

Do **not** set `CMAKE_CXX_FLAGS` globally — FetchContent builds glfw in-tree and
that would instrument it too.

**Default LSan off** for these leaky interactive demos. Add the standard
ASan-guarded weak hook to one TU (e.g. `lib/vermilion.cpp`):

```cpp
#if defined(__SANITIZE_ADDRESS__) || \
    (defined(__has_feature) && __has_feature(address_sanitizer))
extern "C" const char *__asan_default_options(void) { return "detect_leaks=0"; }
#endif
```

(spimulator does the same in `spim.c`.) The gate is for corruption, not the
demos' intentional exit-time leaks. Caveat: `gl3w.c` resolves GL entry points at
runtime — UBSan `function`/`vptr`-via-function-pointer checks across that C/loader
boundary can be noisy; expect to narrow sub-checks or suppress.

## Caveats (be honest about these)

1. **Interactive GL demos needing a display, and OpenGL 4.5.** Each example
   blocks in a GLFW loop until closed; many also *require a 4.5 context* that a
   headless software stack (llvmpipe/Mesa) may not provide, so even an Xvfb/EGL
   smoke run may bail at context creation rather than exercise the code. A
   realistic gate asserts **builds-clean-under-ASan/UBSan** plus, where the
   context can be created, a **headless render-N-frames-then-exit** smoke run.
2. **Largely third-party/upstream code.** `vermilion` and every `src/NN-*`
   example are imported sample code (the warning-suppression flags confirm it),
   and the fetched glfw is fully third-party. Findings are mostly *upstream's*.
   Scope the gate to first-party targets; keep `ASAN_OPTIONS`/`UBSAN_OPTIONS`
   suppressions for noise from linked vendored/driver code.
3. **No test suite.** A smoke harness (headless few-frames-then-exit for a
   representative subset) is a **prerequisite** — it is what makes the *dynamic*
   sanitizers worthwhile. Building it (and getting a 4.5-capable headless
   context, or accepting build-only coverage) is the bulk of the work.
4. **No container template.** Unlike spimulator there's no `make image`/CI to
   hang the second instrumented build on; you'd add scaffold or document a
   manual `cmake -DENABLE_SANITIZERS=ON` + Xvfb recipe.

## Priority / feasibility verdict

**Lower priority than apue/spimulator.** Those are non-interactive, test-backed,
mostly first-party — a sanitizer run over the existing suite is high-signal and
nearly free. Here there's no test suite, no container gate, the demos are
display-bound *and* gated on an OpenGL 4.5 context that headless stacks often
can't supply, and the code is imported sample code whose findings we'd mostly
punt upstream. Flag wiring is small; the **OpenGL-4.5-capable headless harness
is the real cost**, with thin payoff. Treat as a *nice-to-have*. If pursued,
do the cheap, high-certainty half first — add `ENABLE_SANITIZERS`, confirm
`vermilion` + the examples **compile and link clean** under both sanitizers —
and defer any dynamic run-frames gate until a working headless 4.5 context
exists.
