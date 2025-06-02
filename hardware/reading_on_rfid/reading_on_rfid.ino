#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 9           
#define SS_PIN 10          

MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;
MFRC522::StatusCode card_status;

void setup(){
    Serial.begin(9600);                                           
    SPI.begin();                                                 
    mfrc522.PCD_Init();                                             
    Serial.println(F("==== RFID CARD READER ===="));
    Serial.println(F("Place your card near the reader..."));
    Serial.println();
}

void loop(){
    // Default authentication key
    for (byte i = 0; i < 6; i++){
        key.keyByte[i] = 0xFF;
    }

    if (!mfrc522.PICC_IsNewCardPresent()) return;
    if (!mfrc522.PICC_ReadCardSerial()) return;

    Serial.println(F("Card detected!"));
    
    String carPlate = readBlockData(2, "Car Plate");
    String balance  = readBlockData(4, "Balance");

    Serial.println();
    Serial.println(F("===== Card Info ====="));
    Serial.print(F("🚗 Car Plate : "));
    Serial.println(carPlate);
    Serial.print(F("💰 Balance    : "));
    Serial.println(balance);
    Serial.println(F("====================="));
    Serial.println();

    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    delay(2000); // wait before scanning again
}

String readBlockData(byte blockNumber, String label){
    byte buffer[18]; // 16 bytes of data + 2 bytes CRC
    byte bufferSize = sizeof(buffer);

    // Authenticate
    card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, blockNumber, &key, &(mfrc522.uid));
    if (card_status != MFRC522::STATUS_OK) {
        Serial.print("❌ Auth failed for ");
        Serial.print(label);
        Serial.print(": ");
        Serial.println(mfrc522.GetStatusCodeName(card_status));
        return "[Auth Fail]";
    }

    // Read block
    card_status = mfrc522.MIFARE_Read(blockNumber, buffer, &bufferSize);
    if (card_status != MFRC522::STATUS_OK) {
        Serial.print("❌ Read failed for ");
        Serial.print(label);
        Serial.print(": ");
        Serial.println(mfrc522.GetStatusCodeName(card_status));
        return "[Read Fail]";
    }

    // Convert to string
    String data = "";
    for (uint8_t i = 0; i < 16; i++){
        data += (char)buffer[i];
    }
    data.trim(); // Remove extra padding
    return data;
}
