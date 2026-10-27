#include <Arduino.h>
#include <DHT.h> // 或使用你對應的感測器庫 (如 AHT10/BME280)

#define DHTPIN 4      // 感測器腳位
#define DHTTYPE DHT22 // 感測器型號

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();
}

void loop() {
  // 讀取數據
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  // 檢查讀取是否失敗
  if (isnan(h) || isnan(t)) {
    // Serial.println("Failed to read from DHT sensor!"); // 失敗時不輸出格式錯誤的字串
    return;
  }

  // 輸出格式: "溫度,濕度" (例如: 24.5,60.2)
  Serial.print(t);
  Serial.print(",");
  Serial.println(h);

  delay(1000); // 每秒採樣一次，Python 端會自動平滑處理
}
