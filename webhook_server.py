#!/usr/bin/env python3
"""
Webhook server for GitHub webhooks
"""

import json
import subprocess
import os
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

APP_DIR = "/home/vlad/catty-reminders-app"
LOG_FILE = "/home/vlad/deploy.log"
RUN_TESTS = True  

def log_message(message):
    """Логирование сообщений"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    print(log_entry)
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)

def run_command(cmd, cwd=None):
    """Выполнение команды с логированием"""
    log_message(f"Executing: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log_message(f"Error: {result.stderr}")
            return False, result.stderr
        log_message(f"Success: {result.stdout}")
        return True, result.stdout
    except subprocess.TimeoutExpired:
        log_message("Command timed out")
        return False, "Command timed out"
    except Exception as e:
        log_message(f"Exception: {str(e)}")
        return False, str(e)

@app.post("/")
async def handle_webhook(request: Request):
    """Обработчик вебхуков от GitHub"""
    try:
        # Получаем данные вебхука
        payload = await request.json()
        event = request.headers.get("X-GitHub-Event", "ping")
        
        log_message(f"Received {event} event from GitHub")
        
        if event == "ping":
            return JSONResponse({"message": "Webhook is working!"})
        
        if event == "push":
            # Обрабатываем push событие
            return await handle_push_event(payload)
        
        return JSONResponse({"message": f"Event {event} ignored"})
    
    except Exception as e:
        log_message(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
async def handle_push_event(payload):
    """Обработка push события"""
    try:
        branch = payload["ref"].split("/")[-1]
        log_message(f"Processing push to branch: {branch}")
        
        # 1. Останавливаем приложение для обновления
        log_message("Stopping application...")
        run_command("sudo systemctl stop catty-app.service")
        
        # 2. Обновляем код
        log_message("Pulling latest changes...")
        success, output = run_command("git pull", cwd=APP_DIR)
        if not success:
            # Если ошибка - перезапускаем старое приложение
            run_command("sudo systemctl start catty-app.service")
            return JSONResponse({"status": "error", "message": output}, status_code=500)
        
        # 3. Устанавливаем зависимости
        log_message("Installing dependencies...")
        success, output = run_command("./venv/bin/pip install -r requirements.txt", cwd=APP_DIR)
        if not success:
            run_command("sudo systemctl start catty-app.service")
            return JSONResponse({"status": "error", "message": output}, status_code=500)
        
        # 4. Запускаем тесты только если включено
        if RUN_TESTS:
            log_message("Running tests...")
            # Сначала запускаем приложение для тестов
            test_process = subprocess.Popen(["./venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8181"], 
                                          cwd=APP_DIR)
            
            # Ждем запуска приложения
            import time
            time.sleep(5)
            
            # Запускаем тесты
            success, output = run_command("./venv/bin/python -m pytest tests/test_unit.py", cwd=APP_DIR)
            
            # Останавливаем тестовое приложение
            test_process.terminate()
            test_process.wait()
            
            if not success:
                log_message("Tests failed! Deployment aborted.")
                # Запускаем старое приложение
                run_command("sudo systemctl start catty-app.service")
                return JSONResponse({"status": "error", "message": "Tests failed"}, status_code=500)
        else:
            log_message("Tests skipped (RUN_TESTS=False)")
        
        # 5. Перезапускаем сервис приложения
        log_message("Restarting application service...")
        success, output = run_command("sudo systemctl restart catty-app.service")
        if not success:
            return JSONResponse({"status": "error", "message": output}, status_code=500)
        
        log_message("Deployment completed successfully!")
        return JSONResponse({"status": "success", "message": "Application deployed successfully"})
    
    except Exception as e:
        log_message(f"Deployment error: {str(e)}")
        # Пытаемся восстановить приложение
        run_command("sudo systemctl start catty-app.service")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "main":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
