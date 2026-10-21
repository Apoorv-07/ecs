
#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_err.h>

#define TX_CHANNEL 1
#define TX_INTERVAL_MS 100

static const char *TAG = "DORMANT_TX";

// Must match the MAC filtered by the receiver.
static uint8_t raw_packet[64] = {
  0x08, 0x00,                   // Non-QoS data frame
  0x00, 0x00,                   // Duration

  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, // Broadcast destination

  0x24, 0x6F, 0x28, 0xAE, 0x11, 0x22, // Source MAC

  0x24, 0x6F, 0x28, 0xAE, 0x11, 0x22, // BSSID

  0x00, 0x00                    // Sequence control
};

static uint32_t successCount = 0;
static uint32_t errorCount = 0;
static uint32_t totalSuccess = 0;
static uint32_t totalErrors = 0;
static uint32_t lastError = 0;
static uint32_t lastReport = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\nDORMANT_TX_STARTING");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  delay(200);

  // Stop Wi-Fi temporarily so the fixed PHY rate can be configured.
  esp_err_t err = esp_wifi_stop();

  if (err != ESP_OK) {
    Serial.printf("WIFI STOP ERROR: %s\n", esp_err_to_name(err));
    while (true) {
      delay(1000);
    }
  }

  // Configure OFDM at 6 Mbps before restarting Wi-Fi.
  err = esp_wifi_config_80211_tx_rate(
    WIFI_IF_STA,
    WIFI_PHY_RATE_6M
  );

  if (err != ESP_OK) {
    Serial.printf("PHY RATE ERROR: %s\n", esp_err_to_name(err));
    while (true) {
      delay(1000);
    }
  }

  err = esp_wifi_start();

  if (err != ESP_OK) {
    Serial.printf("WIFI START ERROR: %s\n", esp_err_to_name(err));
    while (true) {
      delay(1000);
    }
  }

  WiFi.setSleep(false);
  delay(200);

  Serial.println("PHY_RATE=6Mbps");

  uint8_t txMac[6];

  esp_err_t macErr = esp_wifi_get_mac(WIFI_IF_STA, txMac);

  if (macErr != ESP_OK) {
    Serial.printf("MAC ERROR: %s\n", esp_err_to_name(macErr));
    while (true) {
      delay(1000);
    }
  }

  // Address 2: source MAC
  memcpy(&raw_packet[10], txMac, 6);

  // Address 3: BSSID field in this test frame
  memcpy(&raw_packet[16], txMac, 6);

  Serial.printf(
    "ACTUAL_TX_MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
    txMac[0], txMac[1], txMac[2],
    txMac[3], txMac[4], txMac[5]
  );

  err = esp_wifi_set_channel(
    TX_CHANNEL, WIFI_SECOND_CHAN_NONE
  );

  if (err != ESP_OK) {
    Serial.printf("CHANNEL ERROR: %s\n", esp_err_to_name(err));
    while (true) {
      delay(1000);
    }
  }

  Serial.println("TX_READY channel=1");
  Serial.println("Source MAC: 24:6F:28:AE:11:22");
  lastReport = millis();
}

void loop() {
  esp_err_t err = esp_wifi_80211_tx(
    WIFI_IF_STA,
    raw_packet,
    sizeof(raw_packet),
    true
  );

  if (err == ESP_OK) {
    successCount++;
    totalSuccess++;
  } else {
    errorCount++;
    totalErrors++;
    lastError = err;
  }

  uint32_t now = millis();

  if (now - lastReport >= 5000) {
    Serial.printf(
      "TX_STATS success=%lu errors=%lu total_success=%lu total_errors=%lu\n",
      (unsigned long)successCount,
      (unsigned long)errorCount,
      (unsigned long)totalSuccess,
      (unsigned long)totalErrors
    );

    if (errorCount > 0) {
      Serial.printf(
        "LAST_TX_ERROR: %s\n",
        esp_err_to_name((esp_err_t)lastError)
      );
    }

    successCount = 0;
    errorCount = 0;
    lastError = 0;
    lastReport = now;
  }

  delay(TX_INTERVAL_MS);
}
