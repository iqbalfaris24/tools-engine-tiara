import os
import base64
import json
import asyncio
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from pydantic import BaseModel
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 1. Load Config
load_dotenv()
TIARA_SYNC_KEY_HEX = os.getenv("TIARA_SYNC_KEY")
if not TIARA_SYNC_KEY_HEX or len(TIARA_SYNC_KEY_HEX) != 64:
    raise ValueError("TIARA_SYNC_KEY must be set and be 64 hex chars in .env")

TIARA_SYNC_KEY = bytes.fromhex(TIARA_SYNC_KEY_HEX)

app = FastAPI(title="TIARA Python Engine")

# --- Helper Functions ---

def decrypt_payload(encrypted_base64: str) -> Dict[str, Any]:
    """
    Mendekripsi payload dari Laravel.
    Ekspektasi format: Base64( IV(12) + Tag(16) + Ciphertext(N) )
    """
    try:
        # Decode Base64
        raw_data = base64.b64decode(encrypted_base64)

        # Pisahkan komponen (sesuai urutan di PHP tadi)
        iv = raw_data[:12]
        tag = raw_data[12:28]
        ciphertext = raw_data[28:]

        # Dekripsi menggunakan AES-GCM
        aesgcm = AESGCM(TIARA_SYNC_KEY)
        # Library cryptography python meminta tag digabung di akhir ciphertext
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext + tag, None)

        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception as e:
        print(f"Decryption failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid encrypted payload")

async def run_ssl_deploy_task(data: Dict[str, Any]):
    """
    Simulasi Background Worker.
    Di sini nanti logika Paramiko/SSH Anda berada.
    """
    deployment_id = data.get('data', {}).get('deployment_id')
    print(f"[START] Processing Deployment ID: {deployment_id}")
    
    # Simulasi proses lama
    await asyncio.sleep(5)
    
    print(f"--> Connecting to {data['data']['server_ip']} as {data['data']['ssh_user']}...")
    # ... Logika Paramiko ...
    print(f"--> Uploading certs to {data['data']['cert_path']}...")
    print(f"--> Running restart command: {data['data']['restart_command']}")
    
    print(f"[FINISH] Deployment ID {deployment_id} COMPLETED.")
    # TODO: Kirim Webhook balik ke Laravel untuk update status jadi SUCCESS

# --- API Endpoints ---

class EncryptedRequest(BaseModel):
    payload: str

@app.post("/api/v1/execute")
async def execute_task(req: EncryptedRequest, background_tasks: BackgroundTasks):
    # 1. Dekripsi Payload saat request masuk
    decrypted_data = decrypt_payload(req.payload)

    task_type = decrypted_data.get('task')

    # 2. Routing tugas berdasarkan tipe
    if task_type == 'ssl_deploy':
        # Lempar ke background task agar API langsung merespon OK ke Laravel
        background_tasks.add_task(run_ssl_deploy_task, decrypted_data)
        return {"status": "accepted", "task": task_type}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")

@app.get("/")
def health_check():
    return {"status": "ready", "engine": "TIARA Python"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)