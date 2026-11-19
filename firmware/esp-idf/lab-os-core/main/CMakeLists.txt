get_filename_component(LAB_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
set(LAB_ENTRY "main.c")
if(LAB_OS_CANDIDATE)
  set(LAB_ENTRY "candidate_main.c")
  set(LAB_DIAGNOSTIC_SOURCE "resource_monitor.c")
endif()
set(LAB_VOICE_SOURCES
    "${LAB_ROOT}/components/voice/channel_features.c"
    "${LAB_ROOT}/components/voice/channel_prepare.c"
    "${LAB_ROOT}/components/voice/kws_inference.c")
if(DEFINED LAB_VOICE_LOGMEL_ASSETS AND NOT "${LAB_VOICE_LOGMEL_ASSETS}" STREQUAL "" AND
   DEFINED LAB_VOICE_CONTEXT_ASSETS AND NOT "${LAB_VOICE_CONTEXT_ASSETS}" STREQUAL "")
  message(FATAL_ERROR "Select only one optional voice runtime")
endif()
if(DEFINED LAB_VOICE_CONTEXT_ASSETS AND NOT "${LAB_VOICE_CONTEXT_ASSETS}" STREQUAL "")
  include("${CMAKE_CURRENT_LIST_DIR}/voice_context.cmake")
endif()
if(DEFINED LAB_VOICE_LOGMEL_ASSETS AND NOT "${LAB_VOICE_LOGMEL_ASSETS}" STREQUAL "")
  include("${CMAKE_CURRENT_LIST_DIR}/voice_logmel.cmake")
endif()
idf_component_register(
  SRCS "${LAB_ENTRY}" ${LAB_DIAGNOSTIC_SOURCE} "usb_transfer.c" "board_input.c" "board_display.c" "board_session.c" "flash_volume.c"
       "board_boot.c" "target_storage.c" "board_audio.c" "board_sound.c" "audio_memory.c" "board_wifi.c" "board_network.c" "board_udp.c"
       "${LAB_ROOT}/prototypes/lab-os/native/udp_service.c"
       "${LAB_ROOT}/prototypes/lab-os/native/network_binding.c"
       "${LAB_ROOT}/prototypes/lab-os/native/guest_vm.c"
       "${LAB_ROOT}/prototypes/lab-os/native/audio_service.c"
       "${LAB_ROOT}/prototypes/lab-os/native/audio_binding.c"
       "${LAB_ROOT}/prototypes/lab-os/native/voice_service.c"
       ${LAB_VOICE_SOURCES}
       "${LAB_ROOT}/prototypes/lab-os/native/state_service.c"
       "${LAB_ROOT}/prototypes/lab-os/native/state_binding.c"
       "${LAB_ROOT}/prototypes/lab-os/native/state_lfs.c"
       "${LAB_ROOT}/prototypes/lab-os/native/state_mount.c"
       "${LAB_ROOT}/prototypes/lab-os/native/app_home.c"
       "${LAB_ROOT}/prototypes/lab-os/native/app_store.c"
       "${LAB_ROOT}/prototypes/lab-os/native/app_lfs.c"
       "${LAB_ROOT}/prototypes/lab-os/native/app_transfer.c"
       "${LAB_ROOT}/prototypes/lab-os/native/ui.c"
       "${LAB_ROOT}/prototypes/lab-os/native/input.c"
       "${LAB_ROOT}/prototypes/lab-os/native/run_loop.c"
  INCLUDE_DIRS "${LAB_ROOT}/prototypes/lab-os/native" "${CMAKE_BINARY_DIR}/generated"
               "${LAB_ROOT}/assets/fonts" "${LAB_ROOT}/components/voice"
  REQUIRES wamr lab_littlefs esp_driver_usb_serial_jtag esp_driver_gpio esp_driver_spi esp_lcd
           esp_adc esp_driver_i2s esp_partition spi_flash esp_system freertos mbedtls
           esp_wifi esp_netif esp_event)
if(LAB_VOICE_CONTEXT_ENABLED)
  target_compile_definitions(${COMPONENT_LIB} PRIVATE LAB_VOICE_CONTEXT_DURATION=1)
  target_include_directories(${COMPONENT_LIB} PRIVATE "${LAB_VOICE_CONTEXT_ASSETS}")
endif()
if(LAB_VOICE_LOGMEL_ENABLED)
  target_compile_definitions(${COMPONENT_LIB} PRIVATE LAB_VOICE_LOGMEL=1)
  target_include_directories(${COMPONENT_LIB} PRIVATE "${LAB_VOICE_LOGMEL_ASSETS}")
  set_source_files_properties("${LAB_ROOT}/components/voice/logmel_compact.c"
      PROPERTIES COMPILE_OPTIONS "-ffp-contract=off;-fno-fast-math")
endif()
