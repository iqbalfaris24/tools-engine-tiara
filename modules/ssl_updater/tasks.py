import asyncio
import logging
import paramiko
import io
import httpx
from typing import Dict, Any
from core.config import settings

# Inisialisasi logger khusus untuk modul ini
logger = logging.getLogger(__name__)

async def report_status_to_laravel(log_id: int, status: str, output_log: str):
    """
    Fungsi bantu untuk mengirim laporan balik ke Laravel via Webhook.
    """
    webhook_url = settings.LARAVEL_WEBHOOK_URL
    secret_token = settings.TIARA_SYNC_KEY
    payload = {
        "log_id": log_id,
        "status": status,          # 'SUCCESS' atau 'FAILED'
        "output_log": output_log,  # Log lengkap untuk debugging di UI Laravel
    }
    headers = {
        'X-Engine-Secret': secret_token, 
        'Accept': 'application/json',
    }
    try:
        async with httpx.AsyncClient() as client:
            # Kirim POST request ke Laravel dengan timeout 10 detik
            response = await client.post(webhook_url, json=payload, headers=headers, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Successfully reported status for Deployment {log_id}")
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
    log_id = payload.get('log_id')
    domain_name = data.get('domain_name')
    
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
    # logger.DEBUG(f"cer content{new_cert_content}")
    logger.info(f"cer content{new_cert_content}")

    logger.info(f"[START] Updating SSL Domain: {domain_name} on {server_ip}")
    log_buffer = [] 

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

        # --- STEP 2: BACKUP FILE LAMA (PERBAIKAN) ---
        timestamp = "backup_tiara"
        try:
            # 1. Cek apakah file ada.
            sftp.stat(cert_path) 
            
            # 2. Jika ada, jalankan backup DAN TUNGGU SAMPAI SELESAI
            log_buffer.append(f"File {cert_path} exists. Attempting backup...")
            backup_cmd = f"cp {cert_path} {cert_path}.{timestamp}"
            
            # --- INI CARA MEMBUATNYA MENUNGGU ---
            stdin, stdout, stderr = ssh.exec_command(backup_cmd)
            exit_status = stdout.channel.recv_exit_status() # <-- Ini akan 'blocking'
            
            if exit_status == 0:
                log_buffer.append(f"Backed up old cert to {cert_path}.{timestamp}")
            else:
                err_str = stderr.read().decode().strip()
                log_buffer.append(f"WARNING: Failed to backup file (Code {exit_status}). Error: {err_str}. Proceeding anyway...")

        except (FileNotFoundError, IOError) as e:
            # 3. PERBAIKAN: Tangkap IOError (spt Permission Denied) dan FileNotFoundError
            # Jika file tidak ada ATAU tidak bisa diakses, skip backup.
            log_buffer.append(f"No existing file at {cert_path} or cannot access. Skipping backup.")
            logger.info(f"No existing file at {cert_path} or cannot access. Skipping backup.")
            pass # Lanjutkan ke Step 3

        # --- STEP 3: UPLOAD FILE BARU (VIA TMP) ---
        logger.info("Uploading new SSL files to temporary location...")
        log_buffer.append("Uploading files to /tmp/...")

        # Tentukan lokasi sementara
        tmp_cert_path = f"/tmp/{domain_name}.crt"
        tmp_key_path = f"/tmp/{domain_name}.key"
        tmp_chain_path = f"/tmp/{domain_name}.chain"

        try:
            # Upload Cert ke /tmp/
            if new_cert_content:
                with sftp.open(tmp_cert_path, 'w') as f:
                    f.write(new_cert_content)
                log_buffer.append(f"Uploaded cert to {tmp_cert_path}")
            
            # Upload Key ke /tmp/
            if new_key_content:
                with sftp.open(tmp_key_path, 'w') as f:
                    f.write(new_key_content)
                log_buffer.append(f"Uploaded key to {tmp_key_path}")

            # Upload Chain (jika ada) ke /tmp/
            if chain_path and new_chain_content:
                with sftp.open(tmp_chain_path, 'w') as f:
                    f.write(new_chain_content)
                log_buffer.append(f"Uploaded chain to {tmp_chain_path}")

        except Exception as e:
            # Gagal upload bahkan ke /tmp/
            raise Exception(f"Failed to upload to /tmp/ directory. Error: {e}")
        finally:
            sftp.close() # Kita tutup sftp di sini

        logger.info("Files uploaded to temp. Moving to final destination...")

        # --- STEP 3.5: PINDAHKAN FILE DARI /tmp/ KE LOKASI ASLI (DENGAN SUDO) ---
        
        # Buat daftar perintah yang akan dieksekusi
        move_commands = []
        if new_cert_content:
            move_commands.append(f"sudo mv {tmp_cert_path} {cert_path}")
            move_commands.append(f"sudo chown root:root {cert_path}") # Amankan kepemilikan
            move_commands.append(f"sudo chmod 644 {cert_path}")       # Amankan izin
        
        if new_key_content:
            move_commands.append(f"sudo mv {tmp_key_path} {key_path}")
            move_commands.append(f"sudo chown root:root {key_path}")
            move_commands.append(f"sudo chmod 600 {key_path}") # Key harus lebih ketat
        
        if chain_path and new_chain_content:
            move_commands.append(f"sudo mv {tmp_chain_path} {chain_path}")
            move_commands.append(f"sudo chown root:root {chain_path}")
            move_commands.append(f"sudo chmod 644 {chain_path}")

        # Gabungkan semua perintah jadi satu
        full_move_command = " && ".join(move_commands)
        
        if full_move_command:
            log_buffer.append(f"Executing: {full_move_command}")
            stdin, stdout, stderr = ssh.exec_command(full_move_command)
            exit_status = stdout.channel.recv_exit_status() # Tunggu selesai
            
            if exit_status != 0:
                # GAGAL memindahkan file
                err_str = stderr.read().decode().strip() or stdout.read().decode().strip()
                raise Exception(f"Failed to move files from /tmp/ (Code {exit_status}). Error: {err_str}")

        logger.info("All files moved successfully.")
        log_buffer.append("All files moved successfully.")

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
            
            if err_str:
                log_buffer.append(f"Restart FAILED (Code {exit_status}). Error: {err_str}")
            elif out_str:
                log_buffer.append(f"Restart FAILED (Code {exit_status}). Output: {out_str}")
            else:
                log_buffer.append(f"Restart FAILED (Code {exit_status}). No output from server.")

            final_status = "FAILED"

    except Exception as e:
        logger.exception(f"Deployment failed due to unexpected error: {e}")
        log_buffer.append(f"CRITICAL ERROR: {str(e)}")
        final_status = "FAILED"
    
    finally:
        ssh.close()
        logger.info(f"[FINISH] Deployment ID {domain_name} finished with status: {final_status}")
        
        # --- STEP 5: LAPOR BALIK KE LARAVEL ---
        full_log = "\n".join(log_buffer)
        await report_status_to_laravel(log_id, final_status, full_log)