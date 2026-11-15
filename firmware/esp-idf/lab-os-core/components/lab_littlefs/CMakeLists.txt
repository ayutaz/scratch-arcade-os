get_filename_component(LAB_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../.." ABSOLUTE)
set(LFS_SOURCE "${LAB_ROOT}/.cache/os-littlefs-v2.11.3")
if(NOT EXISTS "${LFS_SOURCE}/lfs.c")
  message(FATAL_ERROR "Get pinned littlefs v2.11.3 first; see the core README")
endif()
idf_component_register(SRCS "${LFS_SOURCE}/lfs.c" "${LFS_SOURCE}/lfs_util.c"
                       INCLUDE_DIRS "${LFS_SOURCE}")
target_compile_definitions(${COMPONENT_LIB} PRIVATE LFS_NO_DEBUG LFS_NO_WARN LFS_NO_ERROR)
