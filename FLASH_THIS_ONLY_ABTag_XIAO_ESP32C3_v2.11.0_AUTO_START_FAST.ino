/*
  ============================================================
  AB Tag Finder — XIAO ESP32-C3 Firmware v2.11.0
  REBUILT: ATOMIC GO START / CLEAN RESET / TAG-OWNED STATE / WIFI-OFF
  ============================================================

  IMPORTANT:
    This is the ONLY firmware file that should be flashed.
    BLE advertising is intentionally kept close to the minimal
    XIAO BLE test that was confirmed working on the real board.

  HARDWARE
  --------
  Seeed Studio XIAO ESP32-C3

  Power:
    BAT+  -> 3.7V single-cell LiPo/Li-ion +
    BAT-  -> battery -
    GND   -> common circuit ground

  LEDs:
    D1 / GPIO3 -> GREEN LED anode
    D2 / GPIO4 -> YELLOW LED anode
    D3 / GPIO5 -> RED LED anode

    The three LED cathodes may share ONE 1k resistor to GND.
    Firmware guarantees that only one stage LED is driven at a time.
    During overdue blinking, only the RED LED is toggled.

  Buzzer:
    D5 / GPIO7 -> 100 ohm series resistor -> low-current ACTIVE buzzer +
    buzzer -   -> GND

    This direct-GPIO design is intended for a low-current 3.3V active buzzer.
    If a buzzer requires high current, use a transistor driver instead.

  Physical button:
    D6 / GPIO21 -> momentary STOP button -> GND
    INPUT_PULLUP, so no external pull-up resistor is required.

  Free pins:
    D4 / GPIO6  -> FREE (no physical START)
    D10/GPIO10  -> FREE (no Dock)

  Antenna:
    External U.FL antenna must be connected for normal BLE operation.

  ============================================================
  WORKFLOW
  ============================================================

  START:
    Android app only. Normal AB assignment automatically STARTS the timer.
    GREEN therefore means the timed cycle is already running.

  Physical STOP:
    Stops FIND/BEEP immediately.
    Does NOT reset timer, mapping, stage, or LEDs.

  RESET:
    Android command only.
    Resets elapsed timer to zero and turns stage LEDs off.

  Timer stages:
      0h .. <24h  -> GREEN solid
     24h .. <48h  -> YELLOW solid
     48h .. <72h  -> RED solid
     >=72h        -> RED BLINKING until RESET

  Overdue blink:
    500ms ON / 500ms OFF.

  ============================================================
  LOCKED BLE PROTOCOL
  ============================================================

  BLE Name:
    TAG-XXXXXXXX (unique 8-hex suffix derived from ESP32 eFuse MAC)

  Service UUID:
    a0140001-7244-5512-0000-000000000001

  Command UUID:
    a0140002-7244-5512-0000-000000000002

  Status UUID:
    a0140003-7244-5512-0000-000000000003

  Commands:
    FIND
    STOP
    STATUS
    PING
    BEEP
    FIND_FORCE
    BEEP_FORCE
    SETAB:12345678
    START:12345678:UNIX_SECONDS
    START                         (legacy compatibility)
    RESET

  Persistent TAG state:
    AB (8 digits), START_UNIX and STARTED are stored in NVS.
    AB + START_UNIX + STARTED are also emitted in manufacturer data
    so another tablet can read the state without a GATT connection.

  FIND:
    200ms ON / 300ms OFF
    Maximum 30 seconds
    Continues after Android disconnect until STOP or timeout.

  BEEP / BEEP_FORCE:
    3 short clock-like pulses (140ms ON / 360ms gap).
    Never a one-second continuous tone.

  Compatibility status fields:
    DOCKED=0
    TIMERFORCE=0
    FORCED=0
  These fields remain for Android compatibility although Dock is not used.

  ============================================================
*/

#include <Arduino.h>
#include <Esp.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ============================================================
// CONFIG
// ============================================================

String tagId = "TAG-00000000";

static const char* SERVICE_UUID =
  "a0140001-7244-5512-0000-000000000001";

static const char* COMMAND_UUID =
  "a0140002-7244-5512-0000-000000000002";

static const char* STATUS_UUID =
  "a0140003-7244-5512-0000-000000000003";

// XIAO ESP32-C3 pin mapping
static const uint8_t PIN_LED_GREEN  = 3;   // D1
static const uint8_t PIN_LED_YELLOW = 4;   // D2
static const uint8_t PIN_LED_RED    = 5;   // D3
static const uint8_t PIN_BUZZER     = 7;   // D5
static const uint8_t PIN_STOP       = 21;  // D6

// D4/GPIO6 = FREE
// D10/GPIO10 = FREE

// Active buzzer is the final hardware target.
#define BUZZER_MODE_ACTIVE 1

// Kept for compatibility/testing if a passive buzzer is ever used.
static const uint32_t PASSIVE_BUZZER_FREQ_HZ = 2500;

// Set to 1 only for quick bench test.
// 15s green, 15s yellow, 15s red, then red blinking.
#define FAST_TEST_MODE 0

#if FAST_TEST_MODE
static const uint64_t GREEN_END_MS  = 15ULL * 1000ULL;
static const uint64_t YELLOW_END_MS = 30ULL * 1000ULL;
static const uint64_t RED_END_MS    = 45ULL * 1000ULL;
#else
static const uint64_t GREEN_END_MS =
  24ULL * 60ULL * 60ULL * 1000ULL;

static const uint64_t YELLOW_END_MS =
  48ULL * 60ULL * 60ULL * 1000ULL;

static const uint64_t RED_END_MS =
  72ULL * 60ULL * 60ULL * 1000ULL;
#endif

static const uint32_t OVERDUE_BLINK_MS = 500;

static const uint32_t FIND_ON_MS  = 200;
static const uint32_t FIND_OFF_MS = 300;
static const uint32_t FIND_MAX_MS = 30000;

// Short clock-like BEEP pattern: beep ... beep ... beep, never one continuous second.
static const uint32_t BEEP_ON_MS = 140;
static const uint32_t BEEP_OFF_MS = 360;
static const uint8_t BEEP_PULSE_COUNT = 3;
static const uint32_t BUTTON_DEBOUNCE_MS = 10;
static const uint32_t PHYSICAL_STOP_LATCH_MS = 5000;
static const uint32_t NVS_SAVE_INTERVAL_MS = 300000; // 5 min: fewer NVS writes
static const uint32_t STATE_SCHEMA_VERSION = 260;
static const uint32_t STATUS_REFRESH_INTERVAL_MS = 1000;

// ============================================================
// GLOBALS
// ============================================================

Preferences prefs;

BLEServer* bleServer = nullptr;
BLECharacteristic* commandCharacteristic = nullptr;
BLECharacteristic* statusCharacteristic = nullptr;

volatile bool bleConnected = false;
volatile bool restartAdvertisingRequested = false;
volatile bool advertisingStateDirty = false;
uint32_t bleDisconnectedAtMs = 0;

// Cycle timer + persistent business identity
bool cycleStarted = false;
uint64_t storedElapsedMs = 0;
uint32_t activeRunStartMs = 0;
String assignedAb = "";
uint32_t startUnixSeconds = 0;

static const uint16_t MANUFACTURER_ID = 0xFFFF;

// Physical STOP debounce
bool lastStopRaw = false;
bool stopStable = false;
uint32_t stopLastChangedMs = 0;
uint32_t physicalStopBlockUntilMs = 0;

// FIND
bool finderActive = false;
bool finderToneOn = false;
uint32_t finderStartedMs = 0;
uint32_t finderPhaseStartedMs = 0;

// BEEP — three short pulses, not a continuous tone.
bool oneShotBeepActive = false;
bool oneShotBeepToneOn = false;
uint8_t oneShotBeepPulsesCompleted = 0;
uint32_t oneShotBeepPhaseStartedMs = 0;

// Passive buzzer compatibility state
bool passivePinState = false;
uint32_t passiveLastToggleUs = 0;

// Periodic tasks
uint32_t lastNvsSaveMs = 0;
uint32_t lastStatusRefreshMs = 0;

// ============================================================
// FORWARD DECLARATIONS
// ============================================================

String buildStatus();
String buildCompactGattStatus();
void publishStatus(bool notifyClient);
void saveState();
void updateLeds();
void stopAllBuzzerActivity();
void updateAdvertisingStateData();
bool isValidAb(const String& ab);

// ============================================================
// BUZZER
// ============================================================

void buzzerPinLow() {
  digitalWrite(PIN_BUZZER, LOW);
  passivePinState = false;
}

void buzzerOutputStart() {
#if BUZZER_MODE_ACTIVE
  digitalWrite(PIN_BUZZER, HIGH);
#else
  passivePinState = true;
  passiveLastToggleUs = micros();
  digitalWrite(PIN_BUZZER, HIGH);
#endif
}

void buzzerOutputStop() {
  buzzerPinLow();
}

void servicePassiveBuzzer() {
#if !BUZZER_MODE_ACTIVE
  bool shouldTone =
    (finderActive && finderToneOn) ||
    (oneShotBeepActive && oneShotBeepToneOn);

  if (!shouldTone) {
    if (passivePinState) {
      buzzerPinLow();
    }
    return;
  }

  const uint32_t halfPeriodUs =
    1000000UL / (PASSIVE_BUZZER_FREQ_HZ * 2UL);

  uint32_t nowUs = micros();

  if (
    (uint32_t)(nowUs - passiveLastToggleUs)
    >= halfPeriodUs
  ) {
    passiveLastToggleUs = nowUs;
    passivePinState = !passivePinState;
    digitalWrite(
      PIN_BUZZER,
      passivePinState ? HIGH : LOW
    );
  }
#endif
}

void stopAllBuzzerActivity() {
  finderActive = false;
  finderToneOn = false;
  oneShotBeepActive = false;
  oneShotBeepToneOn = false;
  oneShotBeepPulsesCompleted = 0;
  buzzerOutputStop();
}

// ============================================================
// TIMER / LED
// ============================================================

void allLedsOff() {
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_YELLOW, LOW);
  digitalWrite(PIN_LED_RED, LOW);
}

uint64_t getElapsedMs() {
  if (!cycleStarted) {
    return storedElapsedMs;
  }

  uint32_t nowMs = millis();
  uint32_t delta = nowMs - activeRunStartMs;

  return storedElapsedMs + (uint64_t)delta;
}

const char* getStageName() {
  if (!cycleStarted) {
    return "WAITING";
  }

  uint64_t elapsed = getElapsedMs();

  if (elapsed < GREEN_END_MS) {
    return "GREEN";
  }

  if (elapsed < YELLOW_END_MS) {
    return "YELLOW";
  }

  if (elapsed < RED_END_MS) {
    return "RED";
  }

  return "RED_BLINK_OVERDUE";
}

void updateLeds() {
  // Locked invariant:
  //   GREEN ON  => timer is already running.
  //   no running timer => all stage LEDs OFF.
  // Normal Android assignment uses the atomic GO packet, so AB assignment and
  // timer start happen in one transaction and GREEN appears immediately.
  allLedsOff();

  if (!cycleStarted) {
    return;
  }

  uint64_t elapsed = getElapsedMs();

  if (elapsed < GREEN_END_MS) {
    digitalWrite(PIN_LED_GREEN, HIGH);
    return;
  }

  if (elapsed < YELLOW_END_MS) {
    digitalWrite(PIN_LED_YELLOW, HIGH);
    return;
  }

  if (elapsed < RED_END_MS) {
    digitalWrite(PIN_LED_RED, HIGH);
    return;
  }

  // After the third 24-hour period:
  // red blinks 500ms ON / 500ms OFF until RESET.
  bool redOn =
    ((millis() / OVERDUE_BLINK_MS) % 2U) == 0U;

  digitalWrite(
    PIN_LED_RED,
    redOn ? HIGH : LOW
  );
}

// ============================================================
// STATUS
// ============================================================

String buildStatus() {
  String s;
  s.reserve(150);

  s += "TAG=";
  s += tagId;

  s += ";AB=";
  s += assignedAb;

  s += ";START_UNIX=";
  s += String(startUnixSeconds);

  s += ";STAGE=";
  s += getStageName();

  s += ";ELAPSED=";

  char elapsedBuffer[24];

  snprintf(
    elapsedBuffer,
    sizeof(elapsedBuffer),
    "%llu",
    (unsigned long long)getElapsedMs()
  );

  s += elapsedBuffer;

  // Compatibility fields. There is no physical Dock in this build.
  s += ";DOCKED=0";

  s += ";STARTED=";
  s += cycleStarted ? "1" : "0";

  s += ";TIMERFORCE=0";

  s += ";FINDER=";
  s += finderActive ? "1" : "0";

  s += ";BEEP=";
  s += oneShotBeepActive ? "1" : "0";

  s += ";FORCED=0";

  return s;
}

String buildCompactGattStatus() {
  // <= 18 bytes even with an assigned AB, safe at the default MTU=23.
  String s;
  s.reserve(18);

  s += "S=";
  s += cycleStarted ? "1" : "0";

  s += ";F=";
  s += finderActive ? "1" : "0";

  s += ";A=";
  if (isValidAb(assignedAb)) {
    s += assignedAb;
  } else {
    s += "-";
  }

  return s;
}

void publishStatus(bool notifyClient) {
  if (statusCharacteristic == nullptr) {
    return;
  }

  String fullStatus = buildStatus();
  String gattStatus = buildCompactGattStatus();

  statusCharacteristic->setValue(gattStatus.c_str());

  Serial.print("[STATUS] ");
  Serial.println(fullStatus);
  Serial.print("[GATT STATUS] ");
  Serial.println(gattStatus);

  if (notifyClient && bleConnected) {
    statusCharacteristic->notify();
  }
}

// ============================================================
// NVS
// ============================================================

void saveState() {
  uint64_t elapsed = getElapsedMs();

  prefs.putUInt("schema", STATE_SCHEMA_VERSION);
  prefs.putBool("started", cycleStarted);
  prefs.putULong64("elapsed", elapsed);
  prefs.putString("ab", assignedAb);
  prefs.putUInt("startunix", startUnixSeconds);

  Serial.print("[NVS] AB=");
  Serial.print(assignedAb);
  Serial.print(" START_UNIX=");
  Serial.print(startUnixSeconds);
  Serial.print(" STARTED=");
  Serial.print(cycleStarted ? 1 : 0);

  Serial.print(" ELAPSED=");
  Serial.println((unsigned long long)elapsed);
}

void clearPersistentCycleState() {
  cycleStarted = false;
  storedElapsedMs = 0;
  activeRunStartMs = millis();
  assignedAb = "";
  startUnixSeconds = 0;

  prefs.putUInt("schema", STATE_SCHEMA_VERSION);
  prefs.putBool("started", false);
  prefs.putULong64("elapsed", 0);
  prefs.putString("ab", "");
  prefs.putUInt("startunix", 0);
}

void restoreState() {
  const uint32_t storedSchema = prefs.getUInt("schema", 0);

  // v2.6.0 intentionally starts from a clean state ONCE when upgrading
  // from older experimental state formats. This removes stale yellow/red
  // timers that survived normal Arduino flashing in NVS. Reflashing v2.6.0
  // later does NOT clear a valid current assignment because schema=260 stays.
  if (storedSchema != STATE_SCHEMA_VERSION) {
    clearPersistentCycleState();
    prefs.putUInt("schema", STATE_SCHEMA_VERSION);
    Serial.print("[NVS MIGRATION] OLD SCHEMA ");
    Serial.print(storedSchema);
    Serial.println(" -> CLEAN STATE / SCHEMA 260");
    return;
  }

  cycleStarted = prefs.getBool("started", false);
  storedElapsedMs = prefs.getULong64("elapsed", 0);
  assignedAb = prefs.getString("ab", "");
  startUnixSeconds = prefs.getUInt("startunix", 0);

  const bool validStoredAb = isValidAb(assignedAb);
  const bool validStart = startUnixSeconds > 0;

  if (!validStoredAb) {
    assignedAb = "";
  }

  // A running cycle without BOTH a valid AB and an absolute START time is
  // invalid in this version. Clear it rather than lighting a stale LED.
  if (cycleStarted && (!validStoredAb || !validStart)) {
    clearPersistentCycleState();
    prefs.putUInt("schema", STATE_SCHEMA_VERSION);
    Serial.println("[NVS RECOVERY] INVALID RUNNING STATE -> CLEARED");
    return;
  }

  if (!cycleStarted) {
    storedElapsedMs = 0;
    startUnixSeconds = 0;
    prefs.putULong64("elapsed", 0);
    prefs.putUInt("startunix", 0);
  }

  activeRunStartMs = millis();

  Serial.print("[NVS RESTORE] AB=");
  Serial.print(assignedAb);
  Serial.print(" START_UNIX=");
  Serial.print(startUnixSeconds);
  Serial.print(" STARTED=");
  Serial.print(cycleStarted ? 1 : 0);
  Serial.print(" ELAPSED=");
  Serial.println((unsigned long long)storedElapsedMs);
}

// ============================================================
// CYCLE
// ============================================================

void hardResetCycle() {
  // Visible response FIRST: buzzer + LEDs OFF before any NVS write.
  stopAllBuzzerActivity();
  allLedsOff();

  cycleStarted = false;
  storedElapsedMs = 0;
  activeRunStartMs = millis();
  assignedAb = "";
  startUnixSeconds = 0;

  prefs.putUInt("schema", STATE_SCHEMA_VERSION);
  prefs.putBool("started", false);
  prefs.putULong64("elapsed", 0);
  prefs.putString("ab", "");
  prefs.putUInt("startunix", 0);

  Serial.println("[CYCLE] RESET + AB CLEARED");

  advertisingStateDirty = true;
  publishStatus(true);
}

bool isValidAb(const String& ab) {
  if (ab.length() != 8) return false;
  for (size_t i = 0; i < ab.length(); ++i) {
    if (ab[i] < '0' || ab[i] > '9') return false;
  }
  return true;
}

void setAssignedAb(const String& ab) {
  if (!isValidAb(ab)) {
    Serial.println("[SETAB] REJECTED - AB MUST BE EXACTLY 8 DIGITS");
    publishStatus(true);
    return;
  }

  if (cycleStarted && assignedAb != ab.c_str()) {
    Serial.println("[SETAB] REJECTED - TIMER RUNNING, RESET FIRST");
    publishStatus(true);
    return;
  }

  assignedAb = ab;

  // SETAB is legacy compatibility only. It may store an AB, but it does NOT
  // light GREEN because GREEN is reserved for a running timer.
  if (!cycleStarted) {
    storedElapsedMs = 0;
    startUnixSeconds = 0;
    prefs.putULong64("elapsed", 0);
    prefs.putUInt("startunix", 0);
  }

  updateLeds();

  prefs.putUInt("schema", STATE_SCHEMA_VERSION);
  prefs.putBool("started", cycleStarted);
  prefs.putString("ab", assignedAb);

  advertisingStateDirty = true;
  Serial.println("[SETAB] LEGACY AB SAVED WITHOUT START - LED STAYS OFF");
  Serial.print("[SETAB] SAVED AB=");
  Serial.println(assignedAb);
  publishStatus(true);
}

void beginCycleAtomic(const String& requestedAb, uint32_t requestedStartUnix) {
  if (!isValidAb(requestedAb) || requestedStartUnix == 0) {
    Serial.println("[GO] REJECTED - INVALID AB OR START TIME");
    publishStatus(true);
    return;
  }

  if (cycleStarted) {
    // Idempotent retry is safe. A different cycle requires RESET first.
    if (assignedAb == requestedAb && startUnixSeconds == requestedStartUnix) {
      Serial.println("[GO] DUPLICATE RETRY -> ALREADY RUNNING");
      updateLeds();
      publishStatus(true);
      return;
    }

    Serial.println("[GO] REJECTED - TIMER RUNNING, RESET FIRST");
    publishStatus(true);
    return;
  }

  assignedAb = requestedAb;
  startUnixSeconds = requestedStartUnix;
  cycleStarted = true;
  storedElapsedMs = 0;
  activeRunStartMs = millis();

  // AUTO-START: assignment and timer start are the same transaction.
  // Visible response FIRST: GREEN immediately, before NVS persistence.
  updateLeds();

  // Persist the atomic AB + time + started state before returning from onWrite().
  saveState();
  advertisingStateDirty = true;

  Serial.print("[GO] STARTED AB=");
  Serial.print(assignedAb);
  Serial.print(" START_UNIX=");
  Serial.println(startUnixSeconds);
  Serial.println("[AUTO START] AB ASSIGNED + TIMER STARTED");
  Serial.println("[LED] GREEN ON = TIMER RUNNING");

  publishStatus(true);
}

void beginCycleLegacy(uint32_t requestedStartUnix = 0) {
  if (!isValidAb(assignedAb) || requestedStartUnix == 0) {
    Serial.println("[START LEGACY] REJECTED - USE GO########HHHHHHHH");
    publishStatus(true);
    return;
  }
  beginCycleAtomic(assignedAb, requestedStartUnix);
}

// ============================================================
// FIND / STOP / BEEP
// ============================================================

bool physicalStopLatchActive() {
  return (int32_t)(physicalStopBlockUntilMs - millis()) > 0;
}

void beginFinder(bool compatibilityForceAlias = false) {
  if (physicalStopLatchActive()) {
    stopAllBuzzerActivity();
    Serial.println("[FIND] BLOCKED BY RECENT PHYSICAL STOP");
    publishStatus(true);
    return;
  }
  oneShotBeepActive = false;

  finderActive = true;
  finderToneOn = true;

  finderStartedMs = millis();
  finderPhaseStartedMs = finderStartedMs;

  buzzerOutputStart();

  Serial.println(
    compatibilityForceAlias
      ? "[FIND_FORCE] STARTED (ALIAS)"
      : "[FIND] STARTED"
  );

  publishStatus(true);
}

void stopFinder() {
  stopAllBuzzerActivity();

  Serial.println("[STOP] FINDER/BEEP STOPPED");

  publishStatus(true);
}

void beginOneShotBeep(bool compatibilityForceAlias = false) {
  if (physicalStopLatchActive()) {
    stopAllBuzzerActivity();
    Serial.println("[BEEP] BLOCKED BY RECENT PHYSICAL STOP");
    publishStatus(true);
    return;
  }
  finderActive = false;
  finderToneOn = false;

  oneShotBeepActive = true;
  oneShotBeepToneOn = true;
  oneShotBeepPulsesCompleted = 0;
  oneShotBeepPhaseStartedMs = millis();

  buzzerOutputStart();

  Serial.println(
    compatibilityForceAlias
      ? "[BEEP_FORCE] STARTED 3x SHORT PULSE (ALIAS)"
      : "[BEEP] STARTED 3x SHORT PULSE"
  );

  publishStatus(true);
}

void updateBuzzerLogic() {
  uint32_t nowMs = millis();

  if (oneShotBeepActive) {
    uint32_t phaseMs = nowMs - oneShotBeepPhaseStartedMs;

    if (oneShotBeepToneOn) {
      if (phaseMs >= BEEP_ON_MS) {
        buzzerOutputStop();
        oneShotBeepToneOn = false;
        oneShotBeepPhaseStartedMs = nowMs;
        oneShotBeepPulsesCompleted++;

        if (oneShotBeepPulsesCompleted >= BEEP_PULSE_COUNT) {
          oneShotBeepActive = false;
          Serial.println("[BEEP] FINISHED 3x SHORT PULSE");
          publishStatus(true);
        }
      }
    }
    else if (phaseMs >= BEEP_OFF_MS) {
      oneShotBeepToneOn = true;
      oneShotBeepPhaseStartedMs = nowMs;
      buzzerOutputStart();
    }

    return;
  }

  if (!finderActive) {
    if (finderToneOn) {
      finderToneOn = false;
      buzzerOutputStop();
    }
    return;
  }

  if (
    (uint32_t)(nowMs - finderStartedMs)
    >= FIND_MAX_MS
  ) {
    Serial.println("[FIND] AUTO STOP 30s");
    stopFinder();
    return;
  }

  uint32_t phaseMs =
    nowMs - finderPhaseStartedMs;

  if (finderToneOn) {
    if (phaseMs >= FIND_ON_MS) {
      finderToneOn = false;
      finderPhaseStartedMs = nowMs;
      buzzerOutputStop();
    }
  }
  else {
    if (phaseMs >= FIND_OFF_MS) {
      finderToneOn = true;
      finderPhaseStartedMs = nowMs;
      buzzerOutputStart();
    }
  }
}

// ============================================================
// PHYSICAL STOP BUTTON
// ============================================================

void updateStopButton() {
  bool rawPressed =
    digitalRead(PIN_STOP) == LOW;

  uint32_t nowMs = millis();

  if (rawPressed != lastStopRaw) {
    lastStopRaw = rawPressed;
    stopLastChangedMs = nowMs;
  }

  if (
    (uint32_t)(nowMs - stopLastChangedMs)
    < BUTTON_DEBOUNCE_MS
  ) {
    return;
  }

  if (stopStable == rawPressed) {
    return;
  }

  stopStable = rawPressed;

  // Only trigger on press edge.
  if (!stopStable) {
    return;
  }

  physicalStopBlockUntilMs = nowMs + PHYSICAL_STOP_LATCH_MS;
  stopAllBuzzerActivity();
  Serial.println("[PHYSICAL STOP] STOP LATCH ACTIVE 5s - BUZZER/FINDER OFF");
  // Timer / LEDs / AB mapping are intentionally untouched.
  publishStatus(true);
}

// ============================================================
// BLE CALLBACKS
// ============================================================

class MyServerCallbacks : public BLEServerCallbacks {

  void onConnect(BLEServer* server) override {
    bleConnected = true;

    Serial.println("[BLE] CONNECTED");

    publishStatus(true);
  }

  void onDisconnect(BLEServer* server) override {
    bleConnected = false;

    // Important:
    // do not stop FIND here.
    // Give the BLE stack time before restarting advertising.
    bleDisconnectedAtMs = millis();
    restartAdvertisingRequested = true;

    Serial.println("[BLE] DISCONNECTED - ADVERTISING RESTART QUEUED");
  }
};

class MyCommandCallbacks : public BLECharacteristicCallbacks {

  void onWrite(BLECharacteristic* c) override {
    auto raw = c->getValue();

    String cmd(raw.c_str());

    cmd.trim();
    cmd.toUpperCase();

    Serial.print("[BLE COMMAND] ");
    Serial.println(cmd);

    if (cmd == "FIND") {
      beginFinder(false);
    }
    else if (cmd == "FIND_FORCE") {
      beginFinder(true);
    }
    else if (cmd == "STOP") {
      stopFinder();
    }
    else if (cmd.startsWith("GO") && cmd.length() == 18) {
      // Robust v2.6 command: GO + 8 decimal AB digits + 8 hex Unix seconds.
      // Total length is exactly 18 bytes, safely below the classic 20-byte ATT payload.
      String ab = cmd.substring(2, 10);
      String epochHex = cmd.substring(10, 18);
      char* endPtr = nullptr;
      uint32_t epoch = (uint32_t)strtoul(epochHex.c_str(), &endPtr, 16);

      if (!isValidAb(ab) || endPtr == nullptr || *endPtr != '\0' || epoch == 0) {
        Serial.println("[GO] REJECTED - BAD 18-BYTE PACKET");
        publishStatus(true);
      } else {
        beginCycleAtomic(ab, epoch);
      }
    }
    else if (cmd.startsWith("SETAB:")) {
      String ab = cmd.substring(6);
      setAssignedAb(ab);
    }
    else if (cmd.startsWith("START:")) {
      // Compatibility only: START:UNIX_SECONDS after SETAB.
      String epochText = cmd.substring(6);
      uint32_t epoch = (uint32_t)strtoul(epochText.c_str(), nullptr, 10);
      beginCycleLegacy(epoch);
    }
    else if (cmd == "START") {
      Serial.println("[START] REJECTED - APP MUST SEND ATOMIC GO PACKET");
      publishStatus(true);
    }
    else if (cmd == "RESET") {
      hardResetCycle();
    }
    else if (cmd == "STATUS") {
      publishStatus(true);
    }
    else if (cmd == "PING") {
      if (statusCharacteristic != nullptr) {
        statusCharacteristic->setValue("PONG");

        if (bleConnected) {
          statusCharacteristic->notify();
        }
      }

      Serial.println("[BLE] PONG");
    }
    else if (cmd == "BEEP") {
      beginOneShotBeep(false);
    }
    else if (cmd == "BEEP_FORCE") {
      beginOneShotBeep(true);
    }
    else {
      Serial.print("[BLE] UNKNOWN COMMAND: ");
      Serial.println(cmd);

      if (statusCharacteristic != nullptr) {
        String errorMessage =
          "ERROR=UNKNOWN_COMMAND;CMD=" + cmd;

        statusCharacteristic->setValue(
          errorMessage.c_str()
        );

        if (bleConnected) {
          statusCharacteristic->notify();
        }
      }
    }
  }
};

// ============================================================
// BLE ADVERTISED TAG STATE
// ============================================================

String buildManufacturerStateData() {
  uint8_t raw[14] = {0};

  // First two bytes are the manufacturer/company ID in little-endian.
  raw[0] = (uint8_t)(MANUFACTURER_ID & 0xFF);
  raw[1] = (uint8_t)((MANUFACTURER_ID >> 8) & 0xFF);

  // Android receives the following 12-byte payload after MANUFACTURER_ID.
  raw[2] = 'A';
  raw[3] = 'B';
  raw[4] = 2;  // protocol version

  uint8_t flags = 0;
  if (isValidAb(assignedAb)) flags |= 0x01;
  if (cycleStarted) flags |= 0x02;
  raw[5] = flags;

  uint32_t abNumber = isValidAb(assignedAb)
    ? (uint32_t)strtoul(assignedAb.c_str(), nullptr, 10)
    : 0;

  raw[6] = (uint8_t)(abNumber & 0xFF);
  raw[7] = (uint8_t)((abNumber >> 8) & 0xFF);
  raw[8] = (uint8_t)((abNumber >> 16) & 0xFF);
  raw[9] = (uint8_t)((abNumber >> 24) & 0xFF);

  raw[10] = (uint8_t)(startUnixSeconds & 0xFF);
  raw[11] = (uint8_t)((startUnixSeconds >> 8) & 0xFF);
  raw[12] = (uint8_t)((startUnixSeconds >> 16) & 0xFF);
  raw[13] = (uint8_t)((startUnixSeconds >> 24) & 0xFF);

  return String((char*)raw, sizeof(raw));
}

void updateAdvertisingStateData() {
  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  if (advertising == nullptr) return;

  BLEAdvertisementData scanResponseData;
  scanResponseData.setName(tagId);
  scanResponseData.setManufacturerData(buildManufacturerStateData());
  advertising->setScanResponseData(scanResponseData);
  advertisingStateDirty = false;
}

void initUniqueTagId() {
  uint64_t efuseMac = ESP.getEfuseMac();
  char idBuffer[13];
  snprintf(
    idBuffer,
    sizeof(idBuffer),
    "TAG-%08lX",
    (unsigned long)(efuseMac & 0xFFFFFFFFULL)
  );
  tagId = String(idBuffer);
}

// ============================================================
// BLE SETUP
// ============================================================

void setupBle() {
  Serial.println("[BLE] INIT - SIMPLE WORKING ADVERTISING MODE");

  // Same basic initialization path as the minimal XIAO BLE test
  // that was confirmed visible by the tablet.
  BLEDevice::init(tagId.c_str());

  bleServer =
    BLEDevice::createServer();

  bleServer->setCallbacks(
    new MyServerCallbacks()
  );

  BLEService* service =
    bleServer->createService(
      SERVICE_UUID
    );

  commandCharacteristic =
    service->createCharacteristic(
      COMMAND_UUID,
      BLECharacteristic::PROPERTY_WRITE |
      BLECharacteristic::PROPERTY_WRITE_NR
    );

  commandCharacteristic->setCallbacks(
    new MyCommandCallbacks()
  );

  statusCharacteristic =
    service->createCharacteristic(
      STATUS_UUID,
      BLECharacteristic::PROPERTY_READ |
      BLECharacteristic::PROPERTY_NOTIFY
    );

  statusCharacteristic->addDescriptor(
    new BLE2902()
  );

  String initialStatus =
    buildCompactGattStatus();

  statusCharacteristic->setValue(
    initialStatus.c_str()
  );

  service->start();

  BLEAdvertising* advertising =
    BLEDevice::getAdvertising();

  // Keep this intentionally simple.
  // Do not use custom min/max advertising intervals here.
  // The confirmed-working XIAO test also used the default interval.
  advertising->addServiceUUID(
    SERVICE_UUID
  );

  advertising->setScanResponse(true);
  updateAdvertisingStateData();

  BLEDevice::startAdvertising();

  Serial.println("[BLE] ADVERTISING STARTED");
  Serial.print("[BLE] NAME: ");
  Serial.println(tagId);
  Serial.print("[BLE] SERVICE: ");
  Serial.println(SERVICE_UUID);
}

void serviceAdvertisingRestart() {
  if (!restartAdvertisingRequested) {
    return;
  }

  // Official Arduino BLE examples give the stack a short delay
  // after disconnect before advertising again.
  if (
    (uint32_t)(millis() - bleDisconnectedAtMs)
    < 150
  ) {
    return;
  }

  restartAdvertisingRequested = false;
  updateAdvertisingStateData();

  BLEDevice::startAdvertising();

  Serial.println("[BLE] ADVERTISING RESTARTED AFTER DISCONNECT");
}

// ============================================================
// POWER: WI-FI ALWAYS OFF IN THIS FIRMWARE
// ============================================================

static void disableWiFiForPowerSaving() {
  // This project communicates through BLE only. Wi-Fi is forced OFF
  // on every boot to reduce power consumption. BLE is NOT disabled.
  WiFi.mode(WIFI_OFF);
  esp_wifi_stop();
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(115200);
  delay(300);

  // Radio policy: Wi-Fi OFF first; BLE is initialized later by setupBle().
  disableWiFiForPowerSaving();
  initUniqueTagId();

  Serial.println();
  Serial.println("========================================");
  Serial.println("AB Tag Finder XIAO ESP32-C3 Firmware v2.11.0");
  Serial.println("========================================");
  Serial.println("[HW] D1=GREEN D2=YELLOW D3=RED");
  Serial.println("[HW] D4=FREE D5=BUZZER D6=PHYSICAL STOP");
  Serial.println("[HW] D10=FREE - NO DOCK");
  Serial.println("[HW] START=ANDROID APP ONLY");
  Serial.print("[BLE] UNIQUE TAG + AB/START STATE ADVERTISING: ");
  Serial.println(tagId);
  Serial.println("[TIMER] >72H = RED BLINK 500/500ms");
  Serial.println("[POWER] 3.7V battery through BAT+/BAT-");

  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);

  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_STOP, INPUT_PULLUP);

  allLedsOff();
  buzzerOutputStop();

  prefs.begin(
    "abtag",
    false
  );

  restoreState();

  if (cycleStarted) {
    Serial.println("[BOOT] SAVED CYCLE -> RESUME");
    activeRunStartMs = millis();
  }
  else {
    Serial.println("[BOOT] WAIT APP START");
    storedElapsedMs = 0;
    allLedsOff();
  }

  updateLeds();

  setupBle();

  publishStatus(false);

  lastNvsSaveMs = millis();
  lastStatusRefreshMs = millis();

#if BUZZER_MODE_ACTIVE
  Serial.println("[BUZZER] MODE = ACTIVE");
#else
  Serial.println("[BUZZER] MODE = PASSIVE 2500Hz");
#endif

  Serial.println("[READY]");
}

// ============================================================
// LOOP
// ============================================================

void loop() {
  updateStopButton();

  updateLeds();

  updateBuzzerLogic();

  servicePassiveBuzzer();

  serviceAdvertisingRestart();

  uint32_t nowMs = millis();

  // Persist running elapsed time every 5 minutes (lower NVS wear).
  if (cycleStarted) {
    if (
      (uint32_t)(nowMs - lastNvsSaveMs)
      >= NVS_SAVE_INTERVAL_MS
    ) {
      lastNvsSaveMs = nowMs;
      saveState();
    }
  }
  else {
    lastNvsSaveMs = nowMs;
  }

  // Keep STATUS characteristic fresh even without notifications.
  if (
    (uint32_t)(nowMs - lastStatusRefreshMs)
    >= STATUS_REFRESH_INTERVAL_MS
  ) {
    lastStatusRefreshMs = nowMs;

    if (statusCharacteristic != nullptr) {
      String s = buildCompactGattStatus();
      statusCharacteristic->setValue(s.c_str());
    }
  }

  delay(1);
}
