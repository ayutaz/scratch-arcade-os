cmake_minimum_required(VERSION 3.16)
# Link-only candidate. This proposal is not an approved device image/layout.
set(LAB_OS_CANDIDATE ON)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../lab-os-core/components"
                         "${CMAKE_CURRENT_LIST_DIR}/../lab-os-core/main")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(lab_os_candidate)
