#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
enum {SPI2_HOST=1,SPI_DMA_CH_AUTO=3};
typedef int spi_host_device_t;
typedef int spi_dma_chan_t;
typedef struct {
 int mosi_io_num,miso_io_num,sclk_io_num,quadwp_io_num,quadhd_io_num;
 int data4_io_num,data5_io_num,data6_io_num,data7_io_num;
 bool data_io_default_level;int max_transfer_sz;uint32_t dma_burst_size,flags;
 int isr_cpu_id,intr_flags;
} spi_bus_config_t;
esp_err_t spi_bus_initialize(spi_host_device_t,const spi_bus_config_t *,spi_dma_chan_t);
esp_err_t spi_bus_free(spi_host_device_t);
void *spi_bus_dma_memory_alloc(spi_host_device_t,size_t,uint32_t);
