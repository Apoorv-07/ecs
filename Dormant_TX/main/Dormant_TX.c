#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"

static const char *TAG = "DORMANT_TX";

// Ek standard raw packet jo hawa me float karega
uint8_t raw_packet[64] = {
    0x08, 0x01, 0x00, 0x00, // Frame control
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, // Receiver MAC (Broadcast)
    0x24, 0x6F, 0x28, 0xAE, 0x11, 0x22, // Transmitter MAC
    0x24, 0x6F, 0x28, 0xAE, 0x11, 0x22, // BSSID
    0x00, 0x00
};

void tx_task(void *pvParameter) {
    uint32_t packet_count = 0;
    while(1) {
        // Bina kisi connection ke seedha hawa me packet inject karna
        esp_wifi_80211_tx(WIFI_IF_STA, raw_packet, sizeof(raw_packet), true);
        packet_count++;
        
        if (packet_count % 10 == 0) { 
            ESP_LOGI(TAG, "TX BROADCAST | Packets sent: %lu | Rate: 10 Hz", packet_count);
        }
        vTaskDelay(100 / portTICK_PERIOD_MS); // Exactly 10 Hz rate
    }
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    
    // Channel 1 fix kar diya
    ESP_ERROR_CHECK(esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE));

    ESP_LOGI(TAG, "TX Broadcast Mode Initialized...");
    xTaskCreate(&tx_task, "tx_task", 4096, NULL, 5, NULL);
}