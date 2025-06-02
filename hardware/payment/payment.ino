#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 9
#define SS_PIN 10

MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;
MFRC522::StatusCode card_status;

bool awaitingUpdate = false;
bool sentReady = false;
String currentPlate = "";
long currentBalance = 0;

// Timeout variables
unsigned long readySentTime = 0;
const unsigned long RESPONSE_TIMEOUT = 10000; // 10 seconds

void setup() {
    Serial.begin(9600);
    SPI.begin();
    mfrc522.PCD_Init();

    for (byte i = 0; i < 6; i++) {
        key.keyByte[i] = 0xFF;
    }

    Serial.println(F("==== PAYMENT MODE RFID ===="));
    Serial.println(F("Place your card near the reader..."));
}

void loop() {
    if (!awaitingUpdate) {
        if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) return;

        currentPlate = readBlockData(2, "Car Plate");
        String balanceStr = readBlockData(4, "Balance");

        // Validate data before proceeding
        if (currentPlate.startsWith("[") || balanceStr.startsWith("[")) {
            Serial.println(F("⚠️ Invalid card data. Try again."));
            mfrc522.PICC_HaltA();
            mfrc522.PCD_StopCrypto1();
            delay(2000);
            return;
        }

        currentBalance = balanceStr.toInt();
        Serial.print(currentPlate);
        Serial.print(",");
        Serial.println(balanceStr);

        awaitingUpdate = true;
        sentReady = false;
    }

    if (awaitingUpdate && !sentReady) {
        Serial.println("READY");
        sentReady = true;
        readySentTime = millis();  // Start the timeout
    }

    if (awaitingUpdate && sentReady) {
        // Timeout handling
        if (millis() - readySentTime > RESPONSE_TIMEOUT) {
            Serial.println("[TIMEOUT] No response from PC. Resetting.");
            awaitingUpdate = false;
            sentReady = false;
            mfrc522.PICC_HaltA();
            mfrc522.PCD_StopCrypto1();
            delay(1000);
            return;
        }

        if (Serial.available()) {
            String response = Serial.readStringUntil('\n');
            response.trim();

            Serial.print("[RECEIVED FROM PC]: ");
            Serial.println(response);

            if (response == "I") {
                Serial.println("[DENIED] Insufficient balance");
            } else {
                Serial.print("[DEBUG] Cleaned response: '");
                Serial.print(response);
                Serial.println("'");

                response.trim();  // Right before toInt()
                long newBalance = response.toInt();
                Serial.print(newBalance);



                if (newBalance >= 0) {
                    Serial.println("[WRITING] New balance to card...");
                    writeBlockData(4, String(newBalance));
                    Serial.println("DONE");
                    Serial.print("[UPDATED] New Balance: ");
                    Serial.println(newBalance);
                } else {
                    Serial.println("[ERROR] Invalid new balance received.");
                }
            }

            awaitingUpdate = false;
            sentReady = false;

            mfrc522.PICC_HaltA();
            mfrc522.PCD_StopCrypto1();
            delay(2000);
        }
    }
}

String readBlockData(byte blockNumber, String label){
    byte buffer[18];
    byte bufferSize = sizeof(buffer);

    card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, blockNumber, &key, &(mfrc522.uid));
    if (card_status != MFRC522::STATUS_OK) {
        Serial.print("❌ Auth failed for ");
        Serial.println(label);
        return "[Auth Fail]";
    }

    card_status = mfrc522.MIFARE_Read(blockNumber, buffer, &bufferSize);
    if (card_status != MFRC522::STATUS_OK) {
        Serial.print("❌ Read failed for ");
        Serial.println(label);
        return "[Read Fail]";
    }

    String data = "";
    for (uint8_t i = 0; i < 16; i++) {
        data += (char)buffer[i];
    }
    data.trim();
    return data;
}

void writeBlockData(byte blockNumber, String data) {
    byte buffer[16];
    data.trim();
    while (data.length() < 16) data += ' ';
    data.substring(0, 16).getBytes(buffer, 16);

    card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, blockNumber, &key, &(mfrc522.uid));
    if (card_status != MFRC522::STATUS_OK) {
        Serial.println("❌ Auth failed on write");
        return;
    }

    card_status = mfrc522.MIFARE_Write(blockNumber, buffer, 16);
    if (card_status != MFRC522::STATUS_OK) {
        Serial.println("❌ Write failed");
    }
}
