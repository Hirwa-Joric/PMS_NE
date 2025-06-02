#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN  9 
#define SS_PIN   10

// State machine states
#define WAITING_FOR_CARD 0
#define CARD_DETECTED 1
#define WAITING_FOR_PLATE 2
#define WAITING_FOR_BALANCE 3
#define WRITING_DATA 4
#define OPERATION_COMPLETE 5

MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;
MFRC522::StatusCode card_status;

// State management
int currentState = WAITING_FOR_CARD;

// Buffers for writing
byte carPlateBuff[16];
byte balanceBuff[16];

// Define RFID data blocks
const byte carPlateBlock = 2;
const byte balanceBlock = 4;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();
  
  // Set default key
  for(byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }
  
  // Clear startup message
  Serial.println(F("CARD_WRITER_READY"));
}

void loop() {
  // State machine implementation
  switch (currentState) {
    
    case WAITING_FOR_CARD:
      Serial.println(F("Place card..."));
      currentState = checkForCard() ? CARD_DETECTED : WAITING_FOR_CARD;
      break;
      
    case CARD_DETECTED:
      Serial.println(F("Card_Detected"));
      // Next state: wait for plate number
      Serial.println(F("Prompt_Plate"));
      flushSerial(); // Clear input buffer
      currentState = WAITING_FOR_PLATE;
      break;
      
    case WAITING_FOR_PLATE:
      if (Serial.available() > 0) {
        Serial.setTimeout(5000L); // Wait up to 5 seconds
        byte len = Serial.readBytesUntil('#', (char *)carPlateBuff, 16);
        if (len > 0 && len <= 7) {
          // Successfully read plate data
          padBuffer(carPlateBuff, len);
          Serial.print(F("Plate_Received:"));
          Serial.println((char*)carPlateBuff);
          
          // Move to balance input state
          Serial.println(F("Prompt_Balance"));
          flushSerial(); // Clear input buffer
          currentState = WAITING_FOR_BALANCE;
        } else {
          Serial.println(F("Invalid_Plate_Format"));
          // Stay in same state
        }
      }
      break;
      
    case WAITING_FOR_BALANCE:
      if (Serial.available() > 0) {
        Serial.setTimeout(5000L); // Wait up to 5 seconds
        byte len = Serial.readBytesUntil('#', (char *)balanceBuff, 16);
        if (len > 0 && len <= 16) {
          // Successfully read balance data
          padBuffer(balanceBuff, len);
          Serial.print(F("Balance_Received:"));
          Serial.println((char*)balanceBuff);
          
          // Move to writing state
          Serial.println(F("Attempting_Write"));
          currentState = WRITING_DATA;
        } else {
          Serial.println(F("Invalid_Balance_Format"));
          // Stay in same state
        }
      }
      break;
      
    case WRITING_DATA:
      // Write to RFID
      Serial.println(F("Write_Started"));
      
      // Write plate data to block 2
      card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, carPlateBlock, &key, &(mfrc522.uid));
      if (card_status != MFRC522::STATUS_OK) {
        Serial.print(F("Auth_Fail:"));
        Serial.println(carPlateBlock);
      } else {
        card_status = mfrc522.MIFARE_Write(carPlateBlock, carPlateBuff, 16);
        if (card_status != MFRC522::STATUS_OK) {
          Serial.print(F("Write_Block_Fail:"));
          Serial.println(carPlateBlock);
        } else {
          Serial.print(F("Write_Block_Success:"));
          Serial.println(carPlateBlock);
        }
      }
      
      // Write balance data to block 4
      card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, balanceBlock, &key, &(mfrc522.uid));
      if (card_status != MFRC522::STATUS_OK) {
        Serial.print(F("Auth_Fail:"));
        Serial.println(balanceBlock);
      } else {
        card_status = mfrc522.MIFARE_Write(balanceBlock, balanceBuff, 16);
        if (card_status != MFRC522::STATUS_OK) {
          Serial.print(F("Write_Block_Fail:"));
          Serial.println(balanceBlock);
        } else {
          Serial.print(F("Write_Block_Success:"));
          Serial.println(balanceBlock);
        }
      }
      
      Serial.println(F("Write_Process_Complete"));
      currentState = OPERATION_COMPLETE;
      break;
      
    case OPERATION_COMPLETE:
      Serial.println(F("Card_Operation_Finished. Remove card to reset."));
      
      // Release the card
      mfrc522.PICC_HaltA();
      mfrc522.PCD_StopCrypto1();
      
      // Wait for card removal
      delay(1000);
      if (!mfrc522.PICC_IsNewCardPresent()) {
        Serial.println(F("Card_Removed. Ready for next operation."));
        currentState = WAITING_FOR_CARD;
      } else {
        Serial.println(F("Card_Still_Present"));
        // Stay in this state until card is removed
      }
      break;
  }
  
  // Small delay to avoid serial buffer overflows
  delay(200);
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

// Helper function to check for card presence
bool checkForCard() {
  // Reset the loop if no new card present
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return false;
  }
  
  // Select one of the cards
  if (!mfrc522.PICC_ReadCardSerial()) {
    return false;
  }
  
  return true;
}
