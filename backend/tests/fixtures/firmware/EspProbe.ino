void setup() {
 Serial.begin(115200); pinMode(4, INPUT_PULLUP); pinMode(2, OUTPUT);
 ledcSetup(0, 1000, 8); ledcAttachPin(18, 0);
 analogReadResolution(12); analogSetAttenuation(ADC_11db);
}
void loop() {
 digitalWrite(2, digitalRead(4)); ledcWrite(0, 128);
 Serial.println(analogRead(34)); delay(1);
}
