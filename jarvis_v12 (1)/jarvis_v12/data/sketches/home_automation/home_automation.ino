/*
  JARVIS V12 — Home Automation Relay Sketch
  Upload this ONCE to your Arduino/ESP32 relay board.
  
  After upload, JARVIS talks to it via USB serial automatically.
  
  Supports:
  - 4-channel relay board (common on Amazon/AliExpress ~₹200)
  - Works on: Arduino Uno, Nano, Mega, ESP32, ESP8266
  
  WIRING:
  Relay 1 (Light)  → Arduino Pin 2
  Relay 2 (Fan)    → Arduino Pin 3
  Relay 3 (AC/TV)  → Arduino Pin 4
  Relay 4 (Custom) → Arduino Pin 5
  
  COMMANDS (sent by JARVIS over USB serial):
  LIGHT_ON  LIGHT_OFF  LIGHT_TOGGLE
  FAN_ON    FAN_OFF    FAN_TOGGLE
  AC_ON     AC_OFF     AC_TOGGLE
  TV_ON     TV_OFF     TV_TOGGLE
  HEATER_ON HEATER_OFF
  RELAY1_ON RELAY1_OFF RELAY2_ON RELAY2_OFF
  RELAY3_ON RELAY3_OFF RELAY4_ON RELAY4_OFF
  ALL_ON    ALL_OFF
  STATUS    (returns current state of all relays)
  
  JARVIS tells you to say:
    "JARVIS, light on karo"  → sends LIGHT_ON
    "fan band karo"          → sends FAN_OFF
    "sab kuch band karo"     → sends ALL_OFF
*/

// Pin definitions — change to match your board
const int RELAY_PINS[] = {2, 3, 4, 5};  // Relay 1,2,3,4
const int NUM_RELAYS    = 4;
bool relayState[4]      = {false, false, false, false};

// For active-LOW relay modules (most cheap relay boards are active-LOW)
// Set RELAY_ON=LOW, RELAY_OFF=HIGH
// For active-HIGH modules: swap to HIGH/LOW
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

String inputBuffer = "";

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(100);
  
  for (int i = 0; i < NUM_RELAYS; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], RELAY_OFF);  // All off on startup
    relayState[i] = false;
  }
  
  Serial.println("JARVIS_HOME_READY");
  Serial.println("Relay board online. Waiting for commands...");
}

void setRelay(int idx, bool on) {
  if (idx < 0 || idx >= NUM_RELAYS) return;
  relayState[idx] = on;
  digitalWrite(RELAY_PINS[idx], on ? RELAY_ON : RELAY_OFF);
}

void toggleRelay(int idx) {
  setRelay(idx, !relayState[idx]);
}

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
  cmd.trim();
  cmd.toUpperCase();
  
  // Individual relay control
  if (cmd == "LIGHT_ON"  || cmd == "RELAY1_ON")  { setRelay(0, true);  Serial.println("OK:LIGHT_ON");  return; }
  if (cmd == "LIGHT_OFF" || cmd == "RELAY1_OFF") { setRelay(0, false); Serial.println("OK:LIGHT_OFF"); return; }
  if (cmd == "LIGHT_TOGGLE")                     { toggleRelay(0);     Serial.println("OK:LIGHT_TOGGLE"); return; }
  
  if (cmd == "FAN_ON"   || cmd == "RELAY2_ON")   { setRelay(1, true);  Serial.println("OK:FAN_ON");   return; }
  if (cmd == "FAN_OFF"  || cmd == "RELAY2_OFF")  { setRelay(1, false); Serial.println("OK:FAN_OFF");  return; }
  if (cmd == "FAN_TOGGLE")                       { toggleRelay(1);     Serial.println("OK:FAN_TOGGLE"); return; }
  
  if (cmd == "AC_ON"    || cmd == "RELAY3_ON")   { setRelay(2, true);  Serial.println("OK:AC_ON");    return; }
  if (cmd == "AC_OFF"   || cmd == "RELAY3_OFF")  { setRelay(2, false); Serial.println("OK:AC_OFF");   return; }
  if (cmd == "TV_ON"    || cmd == "AC_ON")       { setRelay(2, true);  Serial.println("OK:TV_ON");    return; }
  if (cmd == "TV_OFF")                           { setRelay(2, false); Serial.println("OK:TV_OFF");   return; }
  if (cmd == "HEATER_ON")                        { setRelay(2, true);  Serial.println("OK:HEATER_ON"); return; }
  if (cmd == "HEATER_OFF")                       { setRelay(2, false); Serial.println("OK:HEATER_OFF"); return; }
  
  if (cmd == "RELAY4_ON"  || cmd == "CUSTOM_ON") { setRelay(3, true);  Serial.println("OK:RELAY4_ON");  return; }
  if (cmd == "RELAY4_OFF" || cmd == "CUSTOM_OFF"){ setRelay(3, false); Serial.println("OK:RELAY4_OFF"); return; }
  
  // All relays
  if (cmd == "ALL_ON") {
    for (int i = 0; i < NUM_RELAYS; i++) setRelay(i, true);
    Serial.println("OK:ALL_ON");
    return;
  }
  if (cmd == "ALL_OFF") {
    for (int i = 0; i < NUM_RELAYS; i++) setRelay(i, false);
    Serial.println("OK:ALL_OFF");
    return;
  }
  
  // Status
  if (cmd == "STATUS" || cmd == "?" || cmd == "GET_STATUS") {
    Serial.println(getStatus());
    return;
  }
  
  // Unknown — echo back
  Serial.println("ERR:UNKNOWN:" + cmd);
}

void loop() {
  // Read serial commands (newline-terminated)
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        processCommand(inputBuffer);
        inputBuffer = "";
      }
    } else {
      if (inputBuffer.length() < 64) {  // Prevent overflow
        inputBuffer += c;
      }
    }
  }
}
