#pragma once
#include "freertos/FreeRTOS.h"
typedef void *TaskHandle_t;
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t);
