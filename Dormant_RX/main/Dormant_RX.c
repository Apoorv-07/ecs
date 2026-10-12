#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"

static const char *TAG = "DORMANT_RX";

void csi_callback(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf || info->len == 0) {
        return;
    }

    // Jaise hi koi packet dikhega, bina kisi filter ya connection ke print kar dega
    printf("CSI_DATA,%d,", info->rx_ctrl.rssi);
    for (int i = 0; i < info->len; i++) {
        printf("%d", info->buf[i]);
        if (i < info->len - 1) {
            printf(",");
        }
    }
    printf("\n");
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Promiscuous filter on taaki sabhi packets catch ho sakein
    wifi_promiscuous_filter_t filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_DATA | WIFI_PROMIS_FILTER_MASK_MGMT
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    // Channel 1 fix
    ESP_ERROR_CHECK(esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE));

    // CSI callback register karna
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_callback, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));

    ESP_LOGI(TAG, "RX Sniffer Mode Active. Continuous listening without connection...");
}