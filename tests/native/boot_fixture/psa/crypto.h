#pragma once
#include <stdint.h>
#include <stddef.h>
typedef int32_t psa_status_t;
typedef uint32_t psa_algorithm_t;
#define PSA_SUCCESS 0
#define PSA_ALG_SHA_256 ((psa_algorithm_t)0x02000009)
psa_status_t psa_hash_compute(psa_algorithm_t,const uint8_t *,size_t,uint8_t *,size_t,size_t *);
