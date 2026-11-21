void setup() {
  Serial1.begin(115200);
  pinMode(2, INPUT_PULLUP);
  pinMode(3, OUTPUT);
  pinMode(4, OUTPUT);
  analogReadResolution(12);
  analogWriteFreq(1000);
  analogWriteRange(255);
}
void loop() {
  digitalWrite(3, digitalRead(2));
  analogWrite(4, 128);
  Serial1.println(analogRead(A0));
  delay(1);
}
