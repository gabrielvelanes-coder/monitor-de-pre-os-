@echo off
cd /d "%~dp0"
echo Monitor de Preco - acessivel para outros PCs da rede em:
echo   http://192.168.0.33:8000/
echo (deixe esta janela aberta enquanto outras pessoas estiverem usando)
echo.
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --insecure
pause
