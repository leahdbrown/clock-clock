#include <Arduino.h>

#define step_pin 1
#define dir_pin 2
#define enable_pin 3

void setup()
{
  Serial.begin(115200); // fixed baud
  Serial.println("Pico Test Setup");
  pinMode(step_pin, OUTPUT);
  pinMode(dir_pin, OUTPUT);
  pinMode(enable_pin, OUTPUT);

  digitalWrite(enable_pin, LOW); // enable the motor driver
}

void loop()
{
  digitalWrite(dir_pin, HIGH); // set direction

  for (int i = 0; i < 200; i++)
  {
    digitalWrite(step_pin, HIGH);
    delayMicroseconds(500);
    digitalWrite(step_pin, LOW);
    delayMicroseconds(500);
  }

  delay(1000); // wait a second

  digitalWrite(dir_pin, LOW); // set direction opposite

  for (int i = 0; i < 200; i++)
  {
    digitalWrite(step_pin, HIGH);
    delayMicroseconds(500);
    digitalWrite(step_pin, LOW);
    delayMicroseconds(500);
  }

  delay(1000); // wait a second
}