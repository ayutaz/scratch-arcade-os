#pragma once
#include <stdint.h>
#include "esp_err.h"
typedef struct {int id;} esp_flash_t;
extern esp_flash_t *esp_flash_default_chip;
esp_err_t esp_flash_get_size(esp_flash_t *,uint32_t *);
