cmake_minimum_required(VERSION 3.20)

project(vermilion9
        LANGUAGES C CXX
        DESCRIPTION "OpenGL Programming Guide, 9th Edition (Red Book) sample code")

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS Debug Release RelWithDebInfo MinSizeRel)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_DEBUG_POSTFIX "_d")

set(OpenGL_GL_PREFERENCE GLVND)
find_package(OpenGL REQUIRED)
find_package(Threads REQUIRED)
find_package(OpenMP)

# Prefer a system-installed glfw on Linux/macOS; on other platforms (or if the
# system package is missing) fall back to fetching glfw at configure time.
find_package(glfw3 3.3 QUIET CONFIG)
if(NOT glfw3_FOUND)
    message(STATUS "System glfw3 not found; fetching glfw 3.4 via FetchContent")
    include(FetchContent)
    set(GLFW_BUILD_DOCS     OFF CACHE BOOL "" FORCE)
    set(GLFW_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
    set(GLFW_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(GLFW_INSTALL        OFF CACHE BOOL "" FORCE)
    # Default to X11 only on Linux for the fetched build — Wayland needs
    # wayland-scanner which is not always installed. Users who want Wayland
    # should install the distro glfw-devel package instead.
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        set(GLFW_BUILD_WAYLAND OFF CACHE BOOL "" FORCE)
        set(GLFW_BUILD_X11     ON  CACHE BOOL "" FORCE)
    endif()
    FetchContent_Declare(
        glfw
        GIT_REPOSITORY https://github.com/glfw/glfw.git
        GIT_TAG        3.4
        GIT_SHALLOW    TRUE
    )
    FetchContent_MakeAvailable(glfw)
else()
    message(STATUS "Using system glfw3 ${glfw3_VERSION}")
endif()

add_library(vermilion STATIC
    lib/gl3w.c
    lib/LoadShaders.cpp
    lib/targa.cpp
    lib/vdds.cpp
    lib/loadtexture.cpp
    lib/vermilion.cpp
    lib/vbm.cpp
)

target_include_directories(vermilion PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(vermilion PUBLIC
    OpenGL::GL
    glfw
    Threads::Threads
    ${CMAKE_DL_LIBS}
)

if(UNIX AND NOT APPLE)
    target_link_libraries(vermilion PUBLIC rt)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_compile_definitions(vermilion PUBLIC _LINUX)
endif()

# Quiet warnings from upstream sources without papering over real build errors.
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(vermilion PRIVATE
        -Wno-deprecated-declarations
        -Wno-narrowing
        -Wno-write-strings
    )
endif()

set(EXAMPLES
    01-keypress
    01-triangles
    03-drawcommands
    03-instancing
    03-instancing2
    03-instancing3
    03-pointsprites
    03-primitiverestart
    03-xfb
    04-gouraud
    04-gouraud-float
    04-shadowmap
    06-cubemap
    06-load-texture
    06-mipfilters
    06-mipmap
    06-multitexture
    06-statictexture
    06-texturewrapping
    06-volumetexturing
    08-lightmodels
    09-simpletess
    09-teapot
    10-draw-xfb
    10-fur
    10-viewport-array
    11-doublewrite
    11-oit
    11-overdrawcount
    12-imageprocessing
    12-particlesimulator
    12-raytracer
    12-simplecompute
)

foreach(EXAMPLE ${EXAMPLES})
    set(_src ${CMAKE_CURRENT_SOURCE_DIR}/src/${EXAMPLE}/${EXAMPLE}.cpp)
    if(NOT EXISTS ${_src})
        message(WARNING "Skipping ${EXAMPLE}: source not found at ${_src}")
        continue()
    endif()
    add_executable(${EXAMPLE} ${_src})
    target_link_libraries(${EXAMPLE} PRIVATE vermilion)
    set_target_properties(${EXAMPLE} PROPERTIES DEBUG_POSTFIX _d)
    if(OpenMP_CXX_FOUND)
        target_link_libraries(${EXAMPLE} PRIVATE OpenMP::OpenMP_CXX)
    endif()
    if(MSVC AND EXISTS ${PROJECT_SOURCE_DIR}/build/templates/vs2013.vcxproj.user.in)
        configure_file(
            ${PROJECT_SOURCE_DIR}/build/templates/vs2013.vcxproj.user.in
            ${CMAKE_CURRENT_BINARY_DIR}/${EXAMPLE}.vcxproj.user
            @ONLY)
    endif()
endforeach()
