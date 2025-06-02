#include <SPI.h>
#include <MFRC522.h>
#define SS_PIN 10
#define RST_PIN 9

MFRC522 rfid(SS_PIN, RST_PIN); 
MFRC522::MIFARE_Key key; 

byte nuidPICC[4];

void setup() { 
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();
  
  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }
  
  // Send a clear initialization message
  Serial.println(F("RFID_UID_READER_READY"));
}

void loop(){
  // Check for waiting commands
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'R') { // Reset stored card UID
      for (byte i = 0; i < 4; i++) {
        nuidPICC[i] = 0;
      }
      Serial.println(F("UID_MEMORY_RESET"));
    }
  }
  
  // Card detection logic
  if(!rfid.PICC_IsNewCardPresent()){
    return;
  }

  if(!rfid.PICC_ReadCardSerial()){
    return;
  }

  // Get the UID
  Serial.println(F("CARD_DETECTED"));
  Serial.print(F("UID:"));
  printHex(rfid.uid.uidByte, rfid.uid.size);
  Serial.println();
  
  // Store the last detected card
  for (byte i = 0; i < 4; i++) {
    nuidPICC[i] = rfid.uid.uidByte[i];
  }

  // Release the card
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  
  // Indicate we're ready for another card
  Serial.println(F("READER_READY_FOR_NEXT_CARD"));
}

void printHex(byte *buffer, byte bufferSize){
  for (byte i = 0; i < bufferSize; i++){
    Serial.print(buffer[i] < 0x10 ? "0" : "");
    Serial.print(buffer[i], HEX);
  }
}  