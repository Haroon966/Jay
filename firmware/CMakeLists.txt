cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(jay)

# GCC 13 can report false positives in third-party Opus sources from
# esphome/micro-opus (e.g. silk/NLSF2A.c). Keep warnings-as-errors in place
# generally, but do not fail the build on this specific diagnostic.
idf_build_set_property(COMPILE_OPTIONS "-Wno-error=maybe-uninitialized" APPEND)
