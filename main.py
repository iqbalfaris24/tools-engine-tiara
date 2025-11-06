# main.py
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from core.security import decrypt_payload
from modules import get_task_handler
from core.logging_config import setup_logging  # <--- 1. Import ini

# 2. Setup Logging di awal
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="TIARA Engine Base")

class EncryptedRequest(BaseModel):
    payload: str

@app.post("/api/v1/execute")
async def execute_task(req: EncryptedRequest, background_tasks: BackgroundTasks):
    try:
        data = decrypt_payload(req.payload)
        task_type = data.get('task')
        logger.info(f"Received task request: {task_type}") # <--- Contoh log

        task_handler = get_task_handler(task_type)
        background_tasks.add_task(task_handler, data)

        return {"status": "accepted", "task": task_type}

    except ValueError as e:
        logger.warning(f"Invalid payload received: {e}") # <--- Log warning
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Internal Engine Error") # <--- Log error dengan stack trace
        raise HTTPException(status_code=500, detail="Internal Engine Error")

@app.get("/")
def health_check():
    return {"status": "ready", "mode": "Modular Monolith"}