# core/security.py
import base64
import json
from typing import Dict, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .config import settings

def decrypt_payload(encrypted_base64: str) -> Dict[str, Any]:
    try:
        raw_data = base64.b64decode(encrypted_base64)
        iv = raw_data[:12]
        tag = raw_data[12:28]
        ciphertext = raw_data[28:]
        
        aesgcm = AESGCM(settings.SYNC_KEY_BYTES)
        # Cryptography lib butuh tag di akhir ciphertext
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext + tag, None)
        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception as e:
        # Log error detailnya di server, tapi jangan kirim ke client demi keamanan
        print(f"Security Error: {e}") 
        raise ValueError("Invalid encrypted payload")