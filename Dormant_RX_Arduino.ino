
#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_timer.h>
#include <esp_err.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "freertos/portmacro.h"

#define CSI_LEN 128
#define QUEUE_LEN 16
#define WIFI_CHANNEL 1

static const uint8_t TX_MAC[6] = {
  0x68, 0x09, 0x47, 0x5C, 0x2B, 0xF0
};

static QueueHandle_t csiQueue;
static portMUX_TYPE statsMux = portMUX_INITIALIZER_UNLOCKED;
static uint32_t nextSeq = 0;

struct CSIRecord {
  uint32_t seq;
  int64_t timestampUs;
  uint8_t mac[6];
  int8_t rssi;
  int8_t values[CSI_LEN];
};

struct RXStats {
  uint32_t callbacks;
  uint32_t target;
  uint32_t otherMac;
  uint32_t wrongLength;
  uint32_t invalidFirst;
  uint32_t queued;
  uint32_t queueDrops;
  uint32_t promiscData;
  uint32_t promiscTarget;
  uint32_t promiscOther;
};

static RXStats stats = {};

#define INC_STAT(field)                  \
  do {                                   \
    portENTER_CRITICAL(&statsMux);       \
    stats.field++;                       \
    portEXIT_CRITICAL(&statsMux);        \
  } while (0)

void promiscuousCallback(void *buf, wifi_promiscuous_pkt_type_t type) {
  if (buf == nullptr || type != WIFI_PKT_DATA) {
    return;
  }

  wifi_promiscuous_pkt_t *pkt =
      (wifi_promiscuous_pkt_t *)buf;

  if (pkt->rx_ctrl.sig_len < 16) {
    return;
  }

  const uint8_t *frame = pkt->payload;

  INC_STAT(promiscData);

  // Address 2 in an ordinary 802.11 data frame is the source MAC.
  if (memcmp(frame + 10, TX_MAC, 6) == 0) {
    INC_STAT(promiscTarget);
  } else {
    INC_STAT(promiscOther);
  }
}

void csiCallback(void *ctx, wifi_csi_info_t *info) {
  (void)ctx;

  if (info == nullptr || info->buf == nullptr || info->len == 0) {
    return;
  }

  INC_STAT(callbacks);

  if (memcmp(info->mac, TX_MAC, 6) != 0) {
    INC_STAT(otherMac);
    return;
  }

  INC_STAT(target);

  if (info->len != CSI_LEN) {
    INC_STAT(wrongLength);
    return;
  }

  if (info->first_word_invalid) {
    INC_STAT(invalidFirst);
  }

  CSIRecord rec = {};
  rec.seq = ++nextSeq;
  rec.timestampUs = esp_timer_get_time();
  memcpy(rec.mac, info->mac, 6);
  rec.rssi = info->rx_ctrl.rssi;
  memcpy(rec.values, info->buf, CSI_LEN);

  // The first four bytes must not be treated as real CSI
  // when the hardware marks the first word invalid.
  if (info->first_word_invalid) {
    memset(rec.values, 0, 4);
  }

  if (xQueueSend(csiQueue, &rec, 0) == pdTRUE) {
    INC_STAT(queued);
  } else {
    INC_STAT(queueDrops);
  }
}

void outputTask(void *arg) {
  (void)arg;

  CSIRecord rec;
  TickType_t lastStats = xTaskGetTickCount();

  for (;;) {
    if (xQueueReceive(csiQueue, &rec, pdMS_TO_TICKS(100)) == pdTRUE) {
      char line[1024];

      int n = snprintf(
        line, sizeof(line),
        "CSI_DATA,%lu,%lld,%02X:%02X:%02X:%02X:%02X:%02X,%d",
        (unsigned long)rec.seq,
        (long long)rec.timestampUs,
        (unsigned)rec.mac[0],
        (unsigned)rec.mac[1],
        (unsigned)rec.mac[2],
        (unsigned)rec.mac[3],
        (unsigned)rec.mac[4],
        (unsigned)rec.mac[5],
        (int)rec.rssi
      );

      bool valid = n > 0 && (size_t)n < sizeof(line);
      size_t used = valid ? (size_t)n : 0;

      for (int i = 0; valid && i < CSI_LEN; i++) {
        size_t remaining = sizeof(line) - used;

        n = snprintf(
          line + used, remaining,
          ",%d", (int)rec.values[i]
        );

        if (n < 0 || (size_t)n >= remaining) {
          valid = false;
        } else {
          used += (size_t)n;
        }
      }

      if (valid) {
        Serial.println(line);
      }
    }

    TickType_t now = xTaskGetTickCount();

    if ((now - lastStats) >= pdMS_TO_TICKS(5000)) {
      RXStats s;

      portENTER_CRITICAL(&statsMux);
      s = stats;
      memset(&stats, 0, sizeof(stats));
      portEXIT_CRITICAL(&statsMux);

      Serial.printf(
        "RX_STATS callbacks=%lu target=%lu other_mac=%lu "
        "wrong_len=%lu invalid_first=%lu queued=%lu queue_drops=%lu "
        "promisc_data=%lu promisc_target=%lu promisc_other=%lu\n",
        (unsigned long)s.callbacks,
        (unsigned long)s.target,
        (unsigned long)s.otherMac,
        (unsigned long)s.wrongLength,
        (unsigned long)s.invalidFirst,
        (unsigned long)s.queued,
        (unsigned long)s.queueDrops,
        (unsigned long)s.promiscData,
        (unsigned long)s.promiscTarget,
        (unsigned long)s.promiscOther
      );

      lastStats = now;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\nDORMANT_RX_STARTING");

  csiQueue = xQueueCreate(QUEUE_LEN, sizeof(CSIRecord));

  if (csiQueue == nullptr) {
    Serial.println("ERROR: CSI queue creation failed");
    abort();
  }

  // Start Wi-Fi in station mode without connecting to an AP.
  WiFi.mode(WIFI_STA);
  delay(200);

  // Both ESP32 nodes must use channel 1.
  ESP_ERROR_CHECK(
    esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE)
  );

  wifi_promiscuous_filter_t filter = {};
  filter.filter_mask = WIFI_PROMIS_FILTER_MASK_DATA;

  ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));

  ESP_ERROR_CHECK(
    esp_wifi_set_promiscuous_rx_cb(promiscuousCallback)
  );

  ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

  // Request legacy long-training-field CSI.
  wifi_csi_config_t csiConfig = {};
  csiConfig.lltf_en = true;
  csiConfig.htltf_en = false;
  csiConfig.stbc_htltf2_en = false;
  csiConfig.ltf_merge_en = false;
  csiConfig.channel_filter_en = false;
  csiConfig.manu_scale = false;
  csiConfig.shift = 0;

  ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csiConfig));
  ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csiCallback, nullptr));

  if (xTaskCreate(
        outputTask, "csi_output", 4096, nullptr, 4, nullptr
      ) != pdPASS) {
    Serial.println("ERROR: output task creation failed");
    abort();
  }

  ESP_ERROR_CHECK(esp_wifi_set_csi(true));

  Serial.println("RX_READY channel=1 baud=115200");
  Serial.println("Expected TX MAC: 68:09:47:5C:2B:F0");
}

void loop() {
  delay(1000);
}
