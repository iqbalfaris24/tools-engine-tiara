# main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from core.security import decrypt_payload
from modules import get_task_handler

app = FastAPI(title="TIARA Engine Base")

class EncryptedRequest(BaseModel):
    payload: str

@app.post("/api/v1/execute")
async def execute_task(req: EncryptedRequest, background_tasks: BackgroundTasks):
    try:
        # 1. Dekripsi (Terpusat di core)
        data = decrypt_payload(req.payload)
        task_type = data.get('task')

        # 2. Dispatch ke Modul yang Tepat (Terpusat di modules registry)
        task_handler = get_task_handler(task_type)

        # 3. Eksekusi di Background
        background_tasks.add_task(task_handler, data)

        return {"status": "accepted", "task": task_type, "module": task_handler.__module__}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Internal Error: {e}") # Ganti dengan logger yang proper nanti
        raise HTTPException(status_code=500, detail="Internal Engine Error")

@app.get("/")
def health_check():
    return {"status": "ready", "mode": "Modular Monolith"}