/*
  JARVIS V12 — Home Automation for ESP32
  (Same logic, ESP32-compatible pins)
  
  WIRING for ESP32 (38-pin DevKit):
  Relay 1 → GPIO 26
  Relay 2 → GPIO 27
  Relay 3 → GPIO 14
  Relay 4 → GPIO 12
  
  Upload speed: 921600 baud (arduino-cli auto-selects)
  Board: esp32:esp32:esp32
*/

const int RELAY_PINS[] = {26, 27, 14, 12};
const int NUM_RELAYS    = 4;
bool relayState[4]      = {false, false, false, false};
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

String inputBuffer = "";

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < NUM_RELAYS; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
    relayState[i] = false;
  }
  Serial.println("JARVIS_HOME_READY_ESP32");
}

void setRelay(int idx, bool on) {
  if (idx < 0 || idx >= NUM_RELAYS) return;
  relayState[idx] = on;
  digitalWrite(RELAY_PINS[idx], on ? RELAY_ON : RELAY_OFF);
}

void toggleRelay(int idx) { setRelay(idx, !relayState[idx]); }

String getStatus() {
  String s = "STATUS:";
  String names[] = {"LIGHT", "FAN", "AC", "CUSTOM"};
  for (int i = 0; i < NUM_RELAYS; i++) {
    s += names[i] + "=" + (relayState[i] ? "ON" : "OFF");
    if (i < NUM_RELAYS-1) s += ",";
  }
  return s;
}

void processCommand(String cmd) {
  cmd.trim(); cmd.toUpperCase();
  if (cmd == "LIGHT_ON"  || cmd == "RELAY1_ON")  { setRelay(0, true);  Serial.println("OK:LIGHT_ON");  return; }
  if (cmd == "LIGHT_OFF" || cmd == "RELAY1_OFF") { setRelay(0, false); Serial.println("OK:LIGHT_OFF"); return; }
  if (cmd == "LIGHT_TOGGLE")                     { toggleRelay(0);     Serial.println("OK:TOGGLE");    return; }
  if (cmd == "FAN_ON"   || cmd == "RELAY2_ON")   { setRelay(1, true);  Serial.println("OK:FAN_ON");    return; }
  if (cmd == "FAN_OFF"  || cmd == "RELAY2_OFF")  { setRelay(1, false); Serial.println("OK:FAN_OFF");   return; }
  if (cmd == "AC_ON"    || cmd == "RELAY3_ON")   { setRelay(2, true);  Serial.println("OK:AC_ON");     return; }
  if (cmd == "AC_OFF"   || cmd == "RELAY3_OFF")  { setRelay(2, false); Serial.println("OK:AC_OFF");    return; }
  if (cmd == "TV_ON")                            { setRelay(2, true);  Serial.println("OK:TV_ON");     return; }
  if (cmd == "TV_OFF")                           { setRelay(2, false); Serial.println("OK:TV_OFF");    return; }
  if (cmd == "HEATER_ON")                        { setRelay(2, true);  Serial.println("OK:HEATER_ON"); return; }
  if (cmd == "HEATER_OFF")                       { setRelay(2, false); Serial.println("OK:HEATER_OFF");return; }
  if (cmd == "RELAY4_ON")                        { setRelay(3, true);  Serial.println("OK:R4_ON");     return; }
  if (cmd == "RELAY4_OFF")                       { setRelay(3, false); Serial.println("OK:R4_OFF");    return; }
  if (cmd == "ALL_ON")  { for(int i=0;i<NUM_RELAYS;i++) setRelay(i,true);  Serial.println("OK:ALL_ON");  return; }
  if (cmd == "ALL_OFF") { for(int i=0;i<NUM_RELAYS;i++) setRelay(i,false); Serial.println("OK:ALL_OFF"); return; }
  if (cmd == "STATUS" || cmd == "?") { Serial.println(getStatus()); return; }
  Serial.println("ERR:UNKNOWN:" + cmd);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) { processCommand(inputBuffer); inputBuffer = ""; }
    } else if (inputBuffer.length() < 64) {
      inputBuffer += c;
    }
  }
}
