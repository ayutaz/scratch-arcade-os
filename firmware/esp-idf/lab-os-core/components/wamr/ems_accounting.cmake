# WAMR 2.4.5 EMS in-place growth omits its free/high-water counters. Preserve
# upstream checkout and license; compile a hash-checked generated copy instead.
function(lab_wamr_ems_accounting wamr_root output_root output_var)
  set(source "${wamr_root}/core/shared/mem-alloc/ems/ems_alloc.c")
  file(SHA256 "${source}" sha)
  if(NOT sha STREQUAL "f630bf416cc73f12d9385cab30ade05782d8d60792a811e550938b005fd9eba6")
    message(FATAL_ERROR "WAMR EMS accounting overlay: source hash mismatch")
  endif()
  file(READ "${source}" original)
  set(before [=[                    hmu_mark_pinuse(hmu_next);
                }
                UNLOCK_HEAP(heap);
                return obj_old;]=])
  set(after [=[                    hmu_mark_pinuse(hmu_next);
                }
                /* Account for bytes consumed by successful in-place growth. */
                heap->total_free_size -= tot_size - tot_size_old;
                if (heap->current_size - heap->total_free_size > heap->highmark_size)
                    heap->highmark_size = heap->current_size - heap->total_free_size;
                UNLOCK_HEAP(heap);
                return obj_old;]=])
  string(REPLACE "${before}" "${after}" patched "${original}")
  if(patched STREQUAL original)
    message(FATAL_ERROR "WAMR EMS accounting overlay: expected branch absent")
  endif()
  file(MAKE_DIRECTORY "${output_root}")
  set(output "${output_root}/lab_wamr_ems_alloc.c")
  set(previous "")
  if(EXISTS "${output}")
    file(READ "${output}" previous)
  endif()
  if(NOT previous STREQUAL patched)
    file(WRITE "${output}" "${patched}")
  endif()
  set(${output_var} "${output}" PARENT_SCOPE)
endfunction()
