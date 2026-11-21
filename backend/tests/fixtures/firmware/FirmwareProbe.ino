void setup(){Serial.begin(9600);pinMode(13,OUTPUT);pinMode(2,INPUT_PULLUP);pinMode(3,OUTPUT);}
void loop(){int value=analogRead(A0);analogWrite(3,128);digitalWrite(13,digitalRead(2));Serial.println(value);delay(5);}
