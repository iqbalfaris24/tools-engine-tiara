import asyncio
import logging
import paramiko
import io
import httpx
from typing import Dict, Any
from core.config import settings

# Inisialisasi logger khusus untuk modul ini
logger = logging.getLogger(__name__)

async def report_status_to_laravel(deployment_id: int, status: str, output_log: str):
    """
    Fungsi bantu untuk mengirim laporan balik ke Laravel via Webhook.
    """
    webhook_url = settings.LARAVEL_WEBHOOK_URL
    payload = {
        "deployment_id": deployment_id,
        "status": status,          # 'SUCCESS' atau 'FAILED'
        "output_log": output_log,  # Log lengkap untuk debugging di UI Laravel
    }

    try:
        async with httpx.AsyncClient() as client:
            # Kirim POST request ke Laravel dengan timeout 10 detik
            response = await client.post(webhook_url, json=payload, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Successfully reported status for Deployment {deployment_id}")
            else:
                logger.warning(f"Failed to report status to Laravel. Code: {response.status_code}, Body: {response.text}")
    except Exception as e:
        logger.error(f"Error reporting to webhook: {e}")

async def run_ssl_deploy_task(payload: Dict[str, Any]):
    """
    Task utama yang dijalankan di background oleh Celery/FastAPI BackgroundTasks.
    Menerima payload lengkap dari Laravel.
    """
    # 1. Ekstrak data dari payload
    data = payload.get('data', {})
    deployment_id = data.get('deployment_id')
    
    # Data Server & Kredensial
    server_ip = data.get('server_ip')
    server_port = int(data.get('server_port', 22))
    ssh_user = data.get('ssh_user')
    ssh_pass = data.get('ssh_pass_raw')  # Pastikan Laravel mengirim ini (sudah didekripsi atau raw)
    
    # Data Path & Command
    cert_path = data.get('cert_path')
    key_path = data.get('key_path')
    chain_path = data.get('chain_path')
    restart_cmd = data.get('restart_command')

    # KONTEKS PENTING: Laravel HARUS mengirim konten file baru dalam payload
    new_cert_content = data.get('new_cert_content')
    new_key_content = data.get('new_key_content')
    new_chain_content = data.get('new_chain_content') # Opsional

    logger.info(f"[START] SSL Deployment ID: {deployment_id} on {server_ip}")
    log_buffer = [] # Untuk menampung semua log output

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # --- STEP 1: KONEKSI SSH ---
        logger.info(f"Connecting to {server_ip}:{server_port} as {ssh_user}...")
        log_buffer.append(f"Connecting to {server_ip}...")
        
        # Gunakan asyncio.to_thread agar koneksi blocking tidak menghentikan aplikasi utama
        await asyncio.to_thread(ssh.connect, hostname=server_ip, port=server_port, username=ssh_user, password=ssh_pass, timeout=20)
        
        logger.info("SSH Connection established.")
        log_buffer.append("SSH Connection established.")

        # Buka SFTP session untuk transfer file
        sftp = ssh.open_sftp()

        # --- STEP 2: BACKUP FILE LAMA (Opsional tapi Recommended) ---
        # (Logic backup sederhana: rename file existing jika ada)
        timestamp = "backup_tiara"
        try:
            sftp.stat(cert_path) # Cek apakah file ada
            ssh.exec_command(f"cp {cert_path} {cert_path}.{timestamp}")
            log_buffer.append(f"Backed up old cert to {cert_path}.{timestamp}")
        except FileNotFoundError:
            pass # File belum ada, skip backup

        # --- STEP 3: UPLOAD FILE BARU ---
        logger.info("Uploading new SSL files...")
        log_buffer.append("Starting file upload...")

        # Upload Cert
        if new_cert_content:
            with sftp.open(cert_path, 'w') as f:
                f.write(new_cert_content)
            log_buffer.append(f"Uploaded: {cert_path}")
        
        # Upload Key
        if new_key_content:
            with sftp.open(key_path, 'w') as f:
                f.write(new_key_content)
            log_buffer.append(f"Uploaded: {key_path}")

        # Upload Chain (jika ada)
        if chain_path and new_chain_content:
            with sftp.open(chain_path, 'w') as f:
                f.write(new_chain_content)
            log_buffer.append(f"Uploaded: {chain_path}")

        sftp.close()
        logger.info("All files uploaded successfully.")

        # --- STEP 4: RESTART WEB SERVER ---
        logger.info(f"Executing restart command: {restart_cmd}")
        log_buffer.append(f"Executing: {restart_cmd}")

        stdin, stdout, stderr = ssh.exec_command(restart_cmd)
        exit_status = stdout.channel.recv_exit_status() # Tunggu command selesai

        out_str = stdout.read().decode().strip()
        err_str = stderr.read().decode().strip()

        if exit_status == 0:
            logger.info("Web server restarted successfully.")
            log_buffer.append(f"Restart SUCCESS. Output: {out_str}")
            final_status = "SUCCESS"
        else:
            logger.error(f"Web server restart FAILED. Exit code: {exit_status}")
            log_buffer.append(f"Restart FAILED (Code {exit_status}). Error: {err_str}")
            final_status = "FAILED"

    except Exception as e:
        logger.exception(f"Deployment failed due to unexpected error: {e}")
        log_buffer.append(f"CRITICAL ERROR: {str(e)}")
        final_status = "FAILED"
    
    finally:
        ssh.close()
        logger.info(f"[FINISH] Deployment ID {deployment_id} finished with status: {final_status}")
        
        # --- STEP 5: LAPOR BALIK KE LARAVEL ---
        full_log = "\n".join(log_buffer)
        await report_status_to_laravel(deployment_id, final_status, full_log)