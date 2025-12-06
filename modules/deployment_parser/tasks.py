# modules/deployment_parser/tasks.py
import asyncio
import logging
import json
import os
import re
import httpx
import pdfplumber
from typing import Dict, Any, List
from core.config import settings

logger = logging.getLogger(__name__)

# --- Helper Reporting (Bisa dipindah ke core/utils.py agar reusable) ---
async def report_status_to_laravel(log_id: int, status: str, output_log: str, result_data: Dict = None):
    webhook_url = settings.TIARA_WEBHOOK_URL
    secret_token = settings.TIARA_SYNC_KEY
    
    # Kita kirim hasil ekstraksi JSON dalam field 'output_log' (sebagai string) 
    # atau field baru jika Laravel Anda sudah siap menerimanya.
    # Disini saya masukkan ke output_log agar tersimpan di text column database Laravel.
    
    final_output = output_log
    if result_data:
        final_output = json.dumps(result_data, indent=2)

    payload = {
        "log_id": log_id,
        "status": status,
        "output_log": final_output, 
    }
    
    headers = {'X-Engine-Secret': secret_token, 'Accept': 'application/json'}
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload, headers=headers, timeout=10.0)
            logger.info(f"Reported status for Doc Parse {log_id}")
    except Exception as e:
        logger.error(f"Error reporting webhook: {e}")

# --- Logika "Heavy Lifting" Parsing PDF ---
def _extract_data_sync(pdf_path: str) -> Dict[str, Any]:
    """
    Fungsi sinkronus untuk parsing PDF (CPU bound).
    Akan dijalankan di threadpool agar tidak memblokir async loop.
    """
    extracted_data = []
    global_json_files = []
    
    # Regex Patterns
    patterns = {
        "tenant": r"(?i)Tenant\s*[:]?\s*(.*)",
        "version": r"(?i)Version\s*[:]?\s*(.*)",
        "modul": r"(?i)Modul\s*[:]?\s*(.*)",
        "env": r"(?i)Penambahan Env\s*[:]?\s*(.*)",
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        
        # 1. Parsing Block per Service (Split by 'Git Detail' or 'Service')
        # Menggunakan 'Git Detail' sebagai pemisah antar service dalam 1 dokumen
        blocks = re.split(r"(?i)Git Detail", full_text)
        
        # Skip block pertama (biasanya header umum)
        for block in blocks[1:]:
            item = {}
            
            # Helper untuk regex search yang aman
            def get_val(key, text_block):
                match = re.search(patterns[key], text_block)
                if match:
                    return match.group(1).strip().replace(":", "").strip()
                return None

            item['tenant'] = get_val("tenant", block)
            item['version'] = get_val("version", block)
            item['modul'] = get_val("modul", block)
            item['env'] = get_val("env", block) or "None"

            # Validasi minimal: harus ada tenant atau modul
            if item['tenant'] or item['modul']:
                extracted_data.append(item)

        # 2. Parsing Global Json (biasanya di akhir dokumen)
        if "Global Json" in full_text:
            # Cari semua string yang berakhiran .json
            json_matches = re.findall(r"[\w\-\.]+\.json", full_text)
            global_json_files = list(set(json_matches))

        return {
            "services": extracted_data,
            "global_json_updates": global_json_files,
            "raw_text_snippet": full_text[:500] + "..." # Opsional: untuk debug
        }
        
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")

# --- Task Handler Utama ---
async def run_deployment_parse_task(payload: Dict[str, Any]):
    """
    Handler yang dipanggil oleh main.py
    Payload dari Laravel diharapkan berisi:
    {
        "data": {
            "file_url": "http://laravel-app.test/storage/docs/file.pdf",
            OR
            "file_path": "/var/www/html/storage/app/docs/file.pdf" (Jika satu server/volume)
        },
        "log_id": 123
    }
    """
    data = payload.get('data', {})
    log_id = payload.get('log_id')
    
    file_url = data.get('file_url')
    file_path = data.get('file_path') # Opsi jika akses lokal
    
    logger.info(f"[START] Parsing Deployment Doc. Log ID: {log_id}")
    
    temp_filename = f"temp_{log_id}.pdf"
    final_status = "FAILED"
    extraction_result = {}
    error_msg = ""

    try:
        # 1. Dapatkan File PDF (Download atau Copy)
        if file_url:
            logger.info(f"Downloading PDF from {file_url}...")
            async with httpx.AsyncClient() as client:
                resp = await client.get(file_url, timeout=30.0)
                if resp.status_code != 200:
                    raise Exception(f"Failed to download PDF. Status: {resp.status_code}")
                with open(temp_filename, "wb") as f:
                    f.write(resp.content)
            target_file = temp_filename
            
        elif file_path and os.path.exists(file_path):
            logger.info(f"Using local file: {file_path}")
            target_file = file_path
        else:
            raise ValueError("No valid file_url or file_path provided in payload.")

        # 2. Jalankan Logika Ekstraksi (CPU Bound -> run in thread)
        logger.info("Running extraction logic...")
        extraction_result = await asyncio.to_thread(_extract_data_sync, target_file)
        
        logger.info(f"Extraction success. Found {len(extraction_result.get('services', []))} services.")
        final_status = "SUCCESS"

    except Exception as e:
        logger.exception(f"Parsing failed: {e}")
        error_msg = str(e)
        final_status = "FAILED"
    
    finally:
        # 3. Cleanup Temp File
        if file_url and os.path.exists(temp_filename):
            os.remove(temp_filename)

        # 4. Report ke Laravel
        output_content = error_msg if final_status == "FAILED" else ""
        # Jika sukses, output_content kosong, tapi result_data terisi JSON
        await report_status_to_laravel(log_id, final_status, output_content, result_data=extraction_result)