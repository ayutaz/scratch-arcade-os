#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_flash.h"
typedef int esp_partition_type_t;
typedef int esp_partition_subtype_t;
enum {ESP_PARTITION_TYPE_APP=0,ESP_PARTITION_TYPE_DATA=1,ESP_PARTITION_TYPE_ANY=0xff,
 ESP_PARTITION_SUBTYPE_DATA_LITTLEFS=0x83,ESP_PARTITION_SUBTYPE_ANY=0xff};
typedef struct {
 esp_flash_t *flash_chip;esp_partition_type_t type;esp_partition_subtype_t subtype;
 uint32_t address,size,erase_size;char label[17];bool encrypted,readonly;
} esp_partition_t;
typedef struct esp_partition_iterator_opaque_ *esp_partition_iterator_t;
esp_err_t esp_partition_find_err(esp_partition_type_t,esp_partition_subtype_t,const char *,esp_partition_iterator_t *);
const esp_partition_t *esp_partition_get(esp_partition_iterator_t);
esp_partition_iterator_t esp_partition_next(esp_partition_iterator_t);
void esp_partition_iterator_release(esp_partition_iterator_t);
esp_err_t esp_partition_read(const esp_partition_t *,size_t,void *,size_t);
esp_err_t esp_partition_write(const esp_partition_t *,size_t,const void *,size_t);
esp_err_t esp_partition_erase_range(const esp_partition_t *,size_t,size_t);
