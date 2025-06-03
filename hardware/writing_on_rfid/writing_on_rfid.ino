#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN  9 
#define SS_PIN   10  
#define LED_SUCCESS 4  // Green LED pin
#define LED_ERROR 5    // Red LED pin

MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;
MFRC522::StatusCode card_status;

bool cardPresent = false;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();
  
  // Initialize LEDs
  pinMode(LED_SUCCESS, OUTPUT);
  pinMode(LED_ERROR, OUTPUT);
  digitalWrite(LED_SUCCESS, LOW);
  digitalWrite(LED_ERROR, LOW);
  
  Serial.println(F("==== CARD REGISTRATION ===="));
  Serial.println(F("Place your RFID card near the reader..."));
  Serial.println();
}

void loop() {
  // Set default key
  for(byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }

  // Card detection with feedback
  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    if (!cardPresent) {
      cardPresent = true;
      digitalWrite(LED_SUCCESS, HIGH); // Card detected indicator
      Serial.println(F("📶 Card detected!"));
      processCard();
    }
  } else {
    // Check if card was removed
    if (cardPresent) {
      cardPresent = false;
      digitalWrite(LED_SUCCESS, LOW);
      digitalWrite(LED_ERROR, LOW);
      Serial.println(F("🔄 Card removed. Ready for next card."));
    }
    delay(100); // Small delay to prevent CPU overload
  }
}

void processCard() {
  // Buffers for writing
  byte carPlateBuff[16];
  byte balanceBuff[16];
  bool plateValid = false;
  bool balanceValid = false;
  
  // Request car plate with retry logic
  while (!plateValid) {
    Serial.println(F("Enter car plate number (must be exactly 7 characters, e.g., RAG234H), end with #:"));
    Serial.setTimeout(30000L); // Wait up to 30 seconds
    byte len = Serial.readBytesUntil('#', (char *)carPlateBuff, 16);

    // Basic format validation (3 letters, 3 numbers, 1 letter)
    if (len == 7) {
      if (isValidPlateFormat((char*)carPlateBuff)) {
        padBuffer(carPlateBuff, len);
        plateValid = true;
      } else {
        Serial.println(F("❌ Invalid plate format. Must be 3 letters, 3 numbers, 1 letter (e.g., RAG234H)"));
      }
    } else {
      Serial.print(F("❌ Invalid input length (got "));
      Serial.print(len);
      Serial.println(F(" characters). Try again.\n"));
    }
    flushSerial();
  }

  // Request balance with retry logic
  while (!balanceValid) {
    Serial.println(F("Enter balance (numeric only, max 10000), end with #:"));
    Serial.setTimeout(30000L); // Wait up to 30 seconds
    byte len = Serial.readBytesUntil('#', (char *)balanceBuff, 16);

    // Ensure balance is numeric and in valid range
    if (len > 0 && len <= 5) { // 5 digits max (0-10000)
      balanceBuff[len] = '\0'; // Null-terminate for string operations
      String balanceStr = String((char*)balanceBuff);
      
      if (isNumeric(balanceStr) && balanceStr.toInt() >= 0 && balanceStr.toInt() <= 10000) {
        padBuffer(balanceBuff, len);
        balanceValid = true;
      } else {
        Serial.println(F("❌ Invalid balance. Must be a number between 0 and 10000."));
      }
    } else {
      Serial.println(F("❌ Invalid balance input. Try again.\n"));
    }
    flushSerial();
  }

  // Define RFID data blocks
  byte carPlateBlock = 2;
  byte balanceBlock = 4;

  // Write to RFID with verification
  bool writePlateSuccess = writeWithVerification(carPlateBlock, carPlateBuff);
  bool writeBalanceSuccess = writeWithVerification(balanceBlock, balanceBuff);

  Serial.println();
  if (writePlateSuccess && writeBalanceSuccess) {
    Serial.println(F("✅ Card successfully programmed!"));
    Serial.print(F("Car Plate: "));
    Serial.println(String((char*)carPlateBuff).substring(0, 7));
    Serial.print(F("Balance: "));
    Serial.println(String((char*)balanceBuff).toInt());
    
    // Visual success indicator
    blinkLED(LED_SUCCESS, 3, 200);
  } else {
    Serial.println(F("❌ Card programming FAILED. Please try again."));
    
    // Visual error indicator
    blinkLED(LED_ERROR, 3, 200);
  }

  Serial.println(F("🔄 Please remove the card to write again."));
  Serial.println(F("--------------------------\n"));

  // Cleanup
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}

// Verify plate format (3 letters, 3 numbers, 1 letter)
bool isValidPlateFormat(char* plate) {
  if (strlen(plate) != 7) return false;
  
  // First 3 characters should be letters
  for (int i = 0; i < 3; i++) {
    if (!isAlpha(plate[i])) return false;
  }
  
  // Next 3 characters should be digits
  for (int i = 3; i < 6; i++) {
    if (!isDigit(plate[i])) return false;
  }
  
  // Last character should be a letter
  return isAlpha(plate[6]);
}

// Check if a string contains only digits
bool isNumeric(String str) {
  for (unsigned int i = 0; i < str.length(); i++) {
    if (!isDigit(str.charAt(i))) return false;
  }
  return true;
}

// Pad the buffer with spaces up to 16 bytes
void padBuffer(byte* buffer, byte len) {
  for(byte i = len; i < 16; i++) {
    buffer[i] = ' ';
  }
}

// Clear Serial input buffer
void flushSerial() {
  while (Serial.available()) {
    Serial.read();
  }
}

// Write data and verify it was written correctly
bool writeWithVerification(byte block, byte buff[]) {
  // Authenticate with the card
  card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(mfrc522.uid));
  if (card_status != MFRC522::STATUS_OK) {
    Serial.print(F("❌ Authentication failed for block "));
    Serial.print(block);
    Serial.print(F(": "));
    Serial.println(mfrc522.GetStatusCodeName(card_status));
    digitalWrite(LED_ERROR, HIGH);
    return false;
  }
  
  // Write data to the block
  card_status = mfrc522.MIFARE_Write(block, buff, 16);
  if (card_status != MFRC522::STATUS_OK) {
    Serial.print(F("❌ Write failed for block "));
    Serial.print(block);
    Serial.print(F(": "));
    Serial.println(mfrc522.GetStatusCodeName(card_status));
    digitalWrite(LED_ERROR, HIGH);
    return false;
  }
  
  // Read back data for verification
  byte readBuff[18];
  byte len = sizeof(readBuff);
  
  // Re-authenticate (sometimes needed between operations)
  card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(mfrc522.uid));
  if (card_status != MFRC522::STATUS_OK) {
    Serial.println(F("❌ Re-authentication failed during verification"));
    digitalWrite(LED_ERROR, HIGH);
    return false;
  }
  
  // Read the block
  card_status = mfrc522.MIFARE_Read(block, readBuff, &len);
  if (card_status != MFRC522::STATUS_OK) {
    Serial.print(F("❌ Verification read failed for block "));
    Serial.print(block);
    Serial.print(F(": "));
    Serial.println(mfrc522.GetStatusCodeName(card_status));
    digitalWrite(LED_ERROR, HIGH);
    return false;
  }
  
  // Compare written data with read data
  for (byte i = 0; i < 16; i++) {
    if (buff[i] != readBuff[i]) {
      Serial.println(F("❌ Verification failed: Data mismatch"));
      digitalWrite(LED_ERROR, HIGH);
      return false;
    }
  }
  
  Serial.print(F("✅ Data verified for block "));
  Serial.println(block);
  return true;
}

// Blink an LED
void blinkLED(int pin, int times, int delayTime) {
  for (int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH);
    delay(delayTime);
    digitalWrite(pin, LOW);
    delay(delayTime);
  }
}
