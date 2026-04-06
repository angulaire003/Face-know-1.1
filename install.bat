@echo off
title RYDI Assistant — Installation
color 0A
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║       RYDI Assistant — Installation          ║
echo  ╚══════════════════════════════════════════════╝
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (echo [ERREUR] Python manquant. & pause & exit /b 1)

echo [1/5] opencv-contrib-python...
pip install opencv-contrib-python --quiet & echo      OK

echo [2/5] Pillow...
pip install Pillow --quiet & echo      OK

echo [3/5] SpeechRecognition + pyttsx3...
pip install SpeechRecognition pyttsx3 --quiet & echo      OK

echo [4/5] pyaudio...
pip install pyaudio --quiet
if %errorlevel% neq 0 (pip install pipwin --quiet & pipwin install pyaudio --quiet)
echo      OK

echo [5/5] pyautogui  (controle clavier/souris)...
pip install pyautogui --quiet & echo      OK

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║            Installation terminee !           ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo  1. Edite config.json — verifie les chemins de tes apps
echo  2. Copie capture.py et train.py de rydi_face/
echo  3. python calibrate.py  — trouve le bon seuil
echo  4. python assistant.py  — lance l'assistant
echo.
pause
