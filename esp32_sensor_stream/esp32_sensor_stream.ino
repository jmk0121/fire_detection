#include <DHT.h>

#define DHT_PIN 4
#define DHT_TYPE DHT11

// 현재 배선 기준
#define GAS1_PIN 35
#define GAS2_PIN 34

DHT dht(DHT_PIN, DHT_TYPE);

const unsigned long SAMPLE_INTERVAL_MS = 2000;
unsigned long lastSample = 0;

int readAdcAverage(int pin) {
  long sum = 0;
  const int N = 10;

  for (int i = 0; i < N; i++) {
    sum += analogRead(pin);
    delay(3);
  }

  return (int)(sum / N);
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  analogReadResolution(12);  // 0 ~ 4095

  delay(2000);
  Serial.println("SYSTEM_READY");
}

void loop() {
  unsigned long now = millis();

  if (now - lastSample < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSample = now;

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("DHT_ERROR");
    return;
  }

  int gas1Raw = readAdcAverage(GAS1_PIN);
  int gas2Raw = readAdcAverage(GAS2_PIN);

  // Python 전송 형식:
  // DATA,온도,습도,GAS1_RAW,GAS2_RAW
  Serial.print("DATA,");
  Serial.print(temperature, 1);
  Serial.print(",");
  Serial.print(humidity, 1);
  Serial.print(",");
  Serial.print(gas1Raw);
  Serial.print(",");
  Serial.println(gas2Raw);
}
