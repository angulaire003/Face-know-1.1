"""
assistant.py — RYDI Assistant
==============================
Phase 1 : Reconnaissance faciale → vérifie que c'est toi
Phase 2 : Déverrouillé → contrôle vocal complet de la machine

Commandes disponibles (voir commands.json) :
  Apps     → "ouvre chrome", "ouvre vscode", "ferme cette fenêtre"...
  Musique  → "play", "suivant", "volume plus"...
  Dictée   → "écris bonjour" → tape dans n'importe quelle app
  Fichiers → "ouvre mes documents", "ouvre le bureau"...
  Scripts  → "lance astrawatch", "lance le serveur"...
  Système  → "capture d'écran", "copie", "colle", "sauvegarde"...
  Web      → "recherche Paris météo", "ouvre youtube"...

Usage:
    python assistant.py
    python assistant.py --no-face      (skip face ID, debug)
    python assistant.py --no-voice     (face ID only)
    python assistant.py --camera 1
"""

import cv2
import os, sys, json, time, threading, datetime, argparse
import subprocess, webbrowser, shutil, logging
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk
import numpy as np

# ── Imports voix ──────────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    import pyttsx3
    VOICE_OK = True
except ImportError:
    VOICE_OK = False
    print("⚠️  pip install SpeechRecognition pyttsx3 pyaudio")

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTO_OK = True
except ImportError:
    PYAUTO_OK = False
    print("⚠️  pip install pyautogui  (nécessaire pour dictée + touches)")

# ── Chargement config ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json(path):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return json.load(f)

CFG  = load_json("config.json")
CMDS = load_json("commands.json")

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("RYDI")

# ── Palette UI ────────────────────────────────────────────────────────────────
BG      = "#0a0a0a"
BG2     = "#131313"
BG3     = "#1a1a1a"
ACCENT  = "#00e5a0"
ACCENT2 = "#00b37a"
RED     = "#ff4455"
AMBER   = "#ffb84d"
BLUE    = "#4d9fff"
TEXT    = "#e0e0e0"
MUTED   = "#555555"
FONT    = ("Consolas", 10)
FONTB   = ("Consolas", 10, "bold")
FONTL   = ("Consolas", 13, "bold")

# ─────────────────────────────────────────────────────────────────────────────
# TTS
# ─────────────────────────────────────────────────────────────────────────────
class TTS:
    def __init__(self):
        self._lock = threading.Lock()
        self._engine = None
        self.enabled = VOICE_OK
        if self.enabled:
            try:
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", CFG["tts"]["rate"])
                self._engine.setProperty("volume", CFG["tts"]["volume"])
                for v in self._engine.getProperty("voices"):
                    if CFG["tts"]["language_preference"] in v.id.lower():
                        self._engine.setProperty("voice", v.id)
                        break
            except Exception as e:
                log.warning(f"TTS init: {e}")
                self.enabled = False

    def say(self, text, blocking=False):
        log.info(f"TTS: {text}")
        if not self.enabled:
            return
        def _run():
            with self._lock:
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception:
                    pass
        if blocking:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# Moteur de commandes
# ─────────────────────────────────────────────────────────────────────────────
class CommandEngine:
    def __init__(self, tts, ui_log):
        self.tts    = tts
        self.ui_log = ui_log
        self._dictating = False

    def execute(self, text: str) -> bool:
        """Analyse le texte et exécute la commande. Retourne True si trouvé."""
        text = text.lower().strip()
        log.info(f"CMD reçu: '{text}'")
        self.ui_log(f"🎤 {text}")

        # ── Dictée active ──────────────────────────────────────────────────
        if self._dictating:
            if any(k in text for k in ["arrête d'écrire", "stop écriture",
                                        "arrête écriture", "stop dictée"]):
                self._dictating = False
                self.tts.say("Dictée arrêtée.")
                self.ui_log("✏️  Dictée arrêtée")
                return True
            if PYAUTO_OK:
                pyautogui.typewrite(text + " ", interval=0.03)
                self.ui_log(f"✏️  Tapé : {text}")
            return True

        # ── Chercher dans toutes les catégories ───────────────────────────
        for category, commands in CMDS.items():
            if category.startswith("_"):
                continue
            for phrase, action in commands.items():
                if phrase in text:
                    return self._dispatch(action, text)

        # ── Recherche web dynamique ("recherche X") ────────────────────────
        for trigger in ["recherche ", "cherche ", "google "]:
            if text.startswith(trigger):
                query = text[len(trigger):]
                return self._dispatch({"action": "web_search", "_query": query}, text)

        # ── Dictée déclenchée par "écris X" ou "tape X" ───────────────────
        for trigger in ["écris ", "tape ", "saisie "]:
            if text.startswith(trigger):
                to_type = text[len(trigger):]
                if PYAUTO_OK and to_type:
                    pyautogui.typewrite(to_type + " ", interval=0.03)
                    self.ui_log(f"✏️  Tapé : {to_type}")
                    return True

        return False

    def _dispatch(self, action: dict, raw: str) -> bool:
        a = action.get("action", "")

        # ── Ouvrir application ─────────────────────────────────────────────
        if a == "open_app":
            target = action.get("target", "")
            path   = CFG["apps"].get(target, "")
            if path:
                try:
                    subprocess.Popen([path])
                    self.tts.say(f"J'ouvre {target}.")
                    self.ui_log(f"✅ Ouvert : {target}")
                    return True
                except Exception as e:
                    # Essai par nom seul (dans PATH)
                    try:
                        subprocess.Popen(target)
                        self.tts.say(f"J'ouvre {target}.")
                        return True
                    except Exception:
                        self.tts.say(f"Impossible d'ouvrir {target}.")
                        self.ui_log(f"❌ {target} : chemin introuvable")
                        return False
            else:
                self.tts.say(f"{target} n'est pas configuré.")
                return False

        # ── Ouvrir URL ─────────────────────────────────────────────────────
        if a == "open_url":
            url = action.get("url", "")
            webbrowser.open(url)
            self.tts.say(f"J'ouvre {url.replace('https://','')}")
            self.ui_log(f"🌐 {url}")
            return True

        # ── Recherche web ──────────────────────────────────────────────────
        if a == "web_search":
            query = action.get("_query", "") or raw.replace("recherche", "").replace("cherche", "").strip()
            if query:
                webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
                self.tts.say(f"Je cherche {query}.")
                self.ui_log(f"🔍 Recherche : {query}")
            return True

        # ── Ouvrir dossier ─────────────────────────────────────────────────
        if a == "open_folder":
            target = action.get("target", "")
            path   = CFG["folders"].get(target, "")
            path   = os.path.expandvars(path)
            if os.path.exists(path):
                os.startfile(path)
                self.tts.say(f"J'ouvre {target}.")
                self.ui_log(f"📁 {path}")
            else:
                self.tts.say(f"Dossier {target} introuvable.")
            return True

        # ── Lancer script Python ───────────────────────────────────────────
        if a == "run_script":
            target = action.get("target", "")
            path   = CFG["scripts"].get(target, "")
            if path and os.path.exists(path):
                subprocess.Popen(["python", path])
                self.tts.say(f"Je lance {target}.")
                self.ui_log(f"🐍 Script : {target}")
            else:
                self.tts.say(f"Script {target} introuvable. Vérifie config.json.")
                self.ui_log(f"❌ Script manquant : {path}")
            return True

        # ── Musique ────────────────────────────────────────────────────────
        if a == "music" and PYAUTO_OK:
            cmd = action.get("cmd", "")
            keys_map = {
                "play_pause": "playpause",
                "next":       "nexttrack",
                "prev":       "prevtrack",
                "vol_up":     "volumeup",
                "vol_down":   "volumedown",
                "mute":       "volumemute",
            }
            if cmd in keys_map:
                pyautogui.press(keys_map[cmd])
                self.ui_log(f"🎵 {cmd}")
            return True

        # ── Touche(s) clavier ──────────────────────────────────────────────
        if a == "key" and PYAUTO_OK:
            keys = action.get("keys", "")
            pyautogui.hotkey(*keys.split("+"))
            self.ui_log(f"⌨️  {keys}")
            return True

        # ── Fenêtre ────────────────────────────────────────────────────────
        if a == "close_window" and PYAUTO_OK:
            pyautogui.hotkey("alt", "F4")
            self.ui_log("🔴 Fenêtre fermée")
            return True
        if a == "minimize" and PYAUTO_OK:
            pyautogui.hotkey("win", "down")
            return True
        if a == "maximize" and PYAUTO_OK:
            pyautogui.hotkey("win", "up")
            return True

        # ── Dictée ─────────────────────────────────────────────────────────
        if a == "dictate_start":
            self._dictating = True
            self.tts.say("Dictée activée. Parle, je tape.")
            self.ui_log("✏️  Mode dictée activé")
            return True
        if a == "dictate_stop":
            self._dictating = False
            self.tts.say("Dictée arrêtée.")
            return True
        if a == "dictate_clear" and PYAUTO_OK:
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("delete")
            return True

        # ── Système ────────────────────────────────────────────────────────
        if a == "screenshot":
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join("screenshots", f"screen_{ts}.png")
            if PYAUTO_OK:
                img = pyautogui.screenshot()
                img.save(path)
                self.tts.say("Capture sauvegardée.")
                self.ui_log(f"📷 {path}")
            return True
        if a == "lock_screen" and PYAUTO_OK:
            pyautogui.hotkey("win", "l")
            return True
        if a == "sleep":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return True
        if a == "shutdown":
            self.tts.say("Extinction dans 5 secondes.", blocking=True)
            subprocess.run(["shutdown", "/s", "/t", "5"])
            return True
        if a == "restart":
            self.tts.say("Redémarrage dans 5 secondes.", blocking=True)
            subprocess.run(["shutdown", "/r", "/t", "5"])
            return True

        # ── Aide ───────────────────────────────────────────────────────────
        if a == "help":
            msg = ("Commandes disponibles : ouvre une application, "
                   "recherche, musique, écris, ouvre mes documents, "
                   "capture d'écran, copie, colle, sauvegarde.")
            self.tts.say(msg)
            self.ui_log("ℹ️  Aide affichée")
            return True

        if a == "pause_assistant":
            return "pause"
        if a == "resume_assistant":
            return "resume"

        return False

# ─────────────────────────────────────────────────────────────────────────────
# Reconnaissance vocale (thread)
# ─────────────────────────────────────────────────────────────────────────────
class VoiceListener:
    def __init__(self, on_text, on_status):
        self.on_text   = on_text
        self.on_status = on_status
        self._running  = False
        self.enabled   = VOICE_OK
        if self.enabled:
            try:
                self._rec = sr.Recognizer()
                self._rec.energy_threshold       = CFG["voice"]["energy_threshold"]
                self._rec.dynamic_energy_threshold = True
                self._rec.pause_threshold        = CFG["voice"]["pause_threshold"]
                self._mic = sr.Microphone()
            except Exception as e:
                log.warning(f"Mic: {e}")
                self.enabled = False

    def start(self):
        if not self.enabled:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        with self._mic as src:
            self._rec.adjust_for_ambient_noise(src, duration=1.5)
        log.info("🎤 Écoute démarrée")
        while self._running:
            try:
                self.on_status("listening")
                with self._mic as src:
                    audio = self._rec.listen(
                        src, timeout=4,
                        phrase_time_limit=CFG["voice"]["phrase_limit_seconds"]
                    )
                self.on_status("processing")
                text = self._rec.recognize_google(
                    audio, language=CFG["voice"]["language"]
                )
                self.on_text(text)
            except sr.WaitTimeoutError:
                self.on_status("idle")
            except sr.UnknownValueError:
                self.on_status("idle")
            except sr.RequestError as e:
                log.warning(f"API: {e}")
                self.on_status("error")
            except Exception as e:
                log.debug(f"Voice: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Application principale
# ─────────────────────────────────────────────────────────────────────────────
class RYDIAssistant:
    # États
    STATE_LOCKED    = "locked"     # Attente face ID
    STATE_UNLOCKED  = "unlocked"   # Commandes vocales actives
    STATE_PAUSED    = "paused"     # Vocal mis en pause

    def __init__(self, camera=0, no_face=False, no_voice=False):
        self.no_face    = no_face
        self.no_voice   = no_voice
        self.state      = self.STATE_UNLOCKED if no_face else self.STATE_LOCKED
        self.active     = True
        self.last_frame = None
        self.detected   = []
        self.frame_n    = 0
        self.fps        = 0.0
        self.fps_t      = time.time()
        self.confirmed_frames = 0
        self.last_recheck = 0
        self.mic_status = "idle"  # listening / processing / error

        self.tts    = TTS()
        self.engine = CommandEngine(self.tts, self._log)
        self.voice  = VoiceListener(self._on_voice, self._on_mic_status)

        # Chargement modèle face
        if not no_face:
            self._load_face_model(camera)

        self._build_ui()

        if not no_face:
            self.tts.say("Veuillez vous identifier.")
        else:
            self.tts.say("Assistant RYDI prêt. Parlez.")
            self._set_state(self.STATE_UNLOCKED)

        self._start_voice()
        self._update()

    # ── Modèle face ───────────────────────────────────────────────────────────
    def _load_face_model(self, camera):
        mp = CFG["face"]["model_path"]
        if not os.path.exists(mp):
            print("❌ Modèle faciale manquant. Lance train.py.")
            sys.exit(1)
        self.rec      = cv2.face.LBPHFaceRecognizer_create()
        self.rec.read(mp)
        self.labels   = {}
        lp = CFG["face"]["labels_path"]
        if os.path.exists(lp):
            with open(lp) as f:
                for line in f:
                    if ":" in line:
                        i, n = line.strip().split(":", 1)
                        self.labels[int(i)] = n
        self.detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.cap   = cv2.VideoCapture(camera)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.cap.isOpened():
            print(f"❌ Webcam {camera} inaccessible.")
            sys.exit(1)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("RYDI Assistant")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # Titre
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=12, pady=(10,4))
        tk.Label(top, text="RYDI ASSISTANT", bg=BG, fg=ACCENT,
                 font=("Consolas", 14, "bold")).pack(side="left")
        self.lbl_state = tk.Label(top, text="🔒 VERROUILLÉ",
                                  bg=BG, fg=AMBER, font=FONTB)
        self.lbl_state.pack(side="right")

        # Corps
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", padx=12, pady=4)

        # ── Vidéo (si face ID activé)
        if not self.no_face:
            self.canvas = tk.Canvas(body, width=480, height=360,
                                    bg="#000", highlightthickness=1,
                                    highlightbackground=ACCENT2)
            self.canvas.grid(row=0, column=0, rowspan=4, padx=(0,12))

        # ── Panneau droit
        right = tk.Frame(body, bg=BG, width=280)
        right.grid(row=0, column=1, sticky="nsew")

        # Micro status
        tk.Label(right, text="MICROPHONE", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        self.lbl_mic = tk.Label(right, text="⬤  En attente",
                                bg=BG2, fg=MUTED, font=FONTB,
                                anchor="w", padx=8, pady=6)
        self.lbl_mic.pack(fill="x", pady=(2,8))

        # Dernier texte reconnu
        tk.Label(right, text="DERNIÈRE COMMANDE", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        self.lbl_last_cmd = tk.Label(right, text="—",
                                     bg=BG2, fg=TEXT, font=FONT,
                                     anchor="w", padx=8, pady=6,
                                     wraplength=260, justify="left")
        self.lbl_last_cmd.pack(fill="x", pady=(2,8))

        # Identité
        if not self.no_face:
            tk.Label(right, text="IDENTITÉ", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
            self.lbl_id = tk.Label(right, text="En attente...",
                                   bg=BG2, fg=AMBER, font=FONTL,
                                   anchor="center", pady=8)
            self.lbl_id.pack(fill="x", pady=(2,8))

        # Commandes rapides rappel
        tk.Label(right, text="COMMANDES RAPIDES", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        hints_f = tk.Frame(right, bg=BG3)
        hints_f.pack(fill="x", pady=(2,8))
        hints = [
            ("ouvre chrome/vscode/...", ACCENT),
            ("recherche [texte]",       ACCENT),
            ("écris [texte]",           BLUE),
            ("play / suivant / volume", BLUE),
            ("capture d'écran",         ACCENT),
            ("copie / colle / sauvegarde", ACCENT),
            ("éteins le pc / redémarre",  RED),
        ]
        for h, c in hints:
            tk.Label(hints_f, text=f"  ◆ {h}", bg=BG3, fg=c,
                     font=FONT, anchor="w").pack(fill="x", pady=1)

        # Log
        tk.Label(right, text="LOG", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        self.log_box = tk.Text(right, bg=BG2, fg=TEXT, font=("Consolas",9),
                               height=12, width=34, state="disabled",
                               relief="flat", cursor="arrow")
        self.log_box.pack(fill="x")

        # Barre boutons
        btn_row = tk.Frame(self.root, bg=BG)
        btn_row.pack(pady=8)
        def btn(t, cmd, fg=ACCENT):
            b = tk.Button(btn_row, text=t, command=cmd,
                          bg=BG3, fg=fg, font=FONT,
                          relief="flat", padx=12, pady=5,
                          activebackground="#222", cursor="hand2", bd=0)
            b.pack(side="left", padx=5)
        btn("▶  VOCAL ON",   lambda: self._start_voice())
        btn("⏸  VOCAL OFF",  lambda: self._stop_voice(), AMBER)
        btn("✕  QUITTER",    self._quit, RED)

    # ── Boucle update ─────────────────────────────────────────────────────────
    def _update(self):
        if not self.active:
            return

        if not self.no_face:
            ret, frame = self.cap.read()
            if ret:
                self.last_frame = frame.copy()
                self.frame_n   += 1
                now = time.time()
                if now - self.fps_t >= 0.5:
                    self.fps    = self.frame_n / (now - self.fps_t + 1e-9)
                    self.frame_n = 0
                    self.fps_t  = now

                # Vérification faciale
                if self.frame_n % 3 == 0:
                    self._check_face(frame)

                self._draw_and_show(frame)

        self._update_ui()
        self.root.after(20, self._update)

    # ── Face check ───────────────────────────────────────────────────────────
    def _check_face(self, frame):
        SCALE = 0.4
        small = cv2.resize(frame, (0,0), fx=SCALE, fy=SCALE)
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray  = self.clahe.apply(gray)
        faces = self.detector.detectMultiScale(
            gray, 1.1, 5, minSize=(50,50)
        )
        THRESHOLD = CFG["face"]["threshold"]
        s = 1.0 / SCALE
        results = []

        for (x, y, w, h) in faces:
            roi = gray[y:y+h, x:x+w]
            roi = cv2.resize(roi, (160,160))
            label_id, conf = self.rec.predict(roi)
            known = conf < THRESHOLD
            name  = self.labels.get(label_id, "?") if known else "Inconnu"
            conf_pct = round((1 - conf / THRESHOLD) * 100) if known else 0

            results.append({
                "name": name, "conf": conf_pct, "raw": conf,
                "box":  (int(x*s), int(y*s), int(w*s), int(h*s))
            })

        self.detected = results
        known_faces = [r for r in results if r["name"] != "Inconnu"]

        if known_faces:
            self.confirmed_frames += 1
            needed = CFG["face"]["confirm_frames"]
            if self.confirmed_frames >= needed and self.state == self.STATE_LOCKED:
                name = known_faces[0]["name"]
                self._set_state(self.STATE_UNLOCKED)
                self.tts.say(f"Identité confirmée. Bonjour {name}, l'assistant est prêt.")
                self._log(f"✅ Identifié : {name}")
        else:
            self.confirmed_frames = max(0, self.confirmed_frames - 1)
            # Re-lock si inconnu depuis 5s (optionnel)
            # Pour l'instant on ne re-lock pas automatiquement

    # ── Dessin vidéo ─────────────────────────────────────────────────────────
    def _draw_and_show(self, frame):
        out = frame.copy()
        locked = self.state == self.STATE_LOCKED

        for face in self.detected:
            x, y, w, h = face["box"]
            known = face["name"] != "Inconnu"
            color = (30,220,100) if known else (50,80,255)

            cv2.rectangle(out, (x,y), (x+w,y+h), color, 2)
            # Coins
            L = 16
            for cx,cy,dx,dy in [(x,y,1,1),(x+w,y,-1,1),(x,y+h,1,-1),(x+w,y+h,-1,-1)]:
                cv2.line(out,(cx,cy),(cx+dx*L,cy),color,3)
                cv2.line(out,(cx,cy),(cx,cy+dy*L),color,3)

            label = face["name"] if not known else f"{face['name']}  {face['conf']}%"
            (tw,th),_ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.5, 1)
            ly = y+h+22
            cv2.rectangle(out,(x,y+h+2),(x+tw+12,ly),color,-1)
            cv2.putText(out, label, (x+5,ly-5),
                        cv2.FONT_HERSHEY_DUPLEX, 0.5, (0,0,0), 1)

        # HUD
        if locked:
            cv2.rectangle(out, (0,0),(320,50),(0,0,0),-1)
            cv2.putText(out,"🔒 EN ATTENTE D'IDENTIFICATION",(10,22),
                        cv2.FONT_HERSHEY_DUPLEX,0.55,(200,150,0),1)
            n = min(self.confirmed_frames, CFG["face"]["confirm_frames"])
            t = CFG["face"]["confirm_frames"]
            cv2.putText(out,f"Confirmation : {n}/{t}",(10,44),
                        cv2.FONT_HERSHEY_DUPLEX,0.4,(160,160,160),1)
        else:
            cv2.rectangle(out,(0,0),(200,30),(0,0,0),-1)
            cv2.putText(out,"✓ DÉVERROUILLÉ",(10,20),
                        cv2.FONT_HERSHEY_DUPLEX,0.5,(30,220,100),1)

        rgb  = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
        imtk = ImageTk.PhotoImage(Image.fromarray(rgb).resize((480,360)))
        self.canvas.imgtk = imtk
        self.canvas.create_image(0,0,anchor="nw",image=imtk)

    # ── Update widgets ────────────────────────────────────────────────────────
    def _update_ui(self):
        # Micro
        mic_map = {
            "listening":   ("⬤  Écoute...",    ACCENT),
            "processing":  ("⬤  Traitement...", AMBER),
            "idle":        ("⬤  En attente",    MUTED),
            "error":       ("⬤  Erreur API",    RED),
            "off":         ("⬤  Désactivé",     MUTED),
        }
        txt, col = mic_map.get(self.mic_status, ("⬤  —", MUTED))
        self.lbl_mic.config(text=txt, fg=col)

        # État
        state_map = {
            self.STATE_LOCKED:   ("🔒 VERROUILLÉ",  AMBER),
            self.STATE_UNLOCKED: ("🔓 DÉVERROUILLÉ", ACCENT),
            self.STATE_PAUSED:   ("⏸ EN PAUSE",     MUTED),
        }
        txt, col = state_map.get(self.state, ("—", MUTED))
        self.lbl_state.config(text=txt, fg=col)

        # Identité
        if not self.no_face and hasattr(self, "lbl_id"):
            known = [r for r in self.detected if r["name"] != "Inconnu"]
            if known:
                self.lbl_id.config(text=f"✓ {known[0]['name']}", fg=ACCENT)
            else:
                self.lbl_id.config(text="Inconnu", fg=RED)

    # ── Voix ─────────────────────────────────────────────────────────────────
    def _on_voice(self, text: str):
        self.lbl_last_cmd.config(text=text)
        if self.state != self.STATE_UNLOCKED:
            return
        result = self.engine.execute(text)
        if result == "pause":
            self._set_state(self.STATE_PAUSED)
            self.tts.say("Assistant en pause.")
        elif result == "resume":
            self._set_state(self.STATE_UNLOCKED)
            self.tts.say("Assistant reprend.")
        elif not result:
            self._log(f"❓ Non reconnu : {text}")

    def _on_mic_status(self, status: str):
        self.mic_status = status

    def _start_voice(self):
        if not self.voice.enabled:
            self._log("⚠️  Micro non disponible")
            return
        self.voice.start()
        self.mic_status = "idle"
        self._log("🎤 Écoute vocale démarrée")

    def _stop_voice(self):
        self.voice.stop()
        self.mic_status = "off"
        self._log("🎤 Écoute vocale arrêtée")

    def _set_state(self, state: str):
        self.state = state
        log.info(f"État → {state}")

    def _log(self, msg: str):
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_box.config(state="normal")
        self.log_box.insert("end", line)
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        log.info(msg)

    def _quit(self):
        self.active = False
        self.voice.stop()
        if not self.no_face and hasattr(self, "cap"):
            self.cap.release()
        cv2.destroyAllWindows()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera",   type=int,  default=CFG.get("camera_index",0))
    ap.add_argument("--no-face",  action="store_true", help="Sauter Face ID (debug)")
    ap.add_argument("--no-voice", action="store_true", help="Désactiver le micro")
    args = ap.parse_args()
    RYDIAssistant(camera=args.camera,
                  no_face=args.no_face,
                  no_voice=args.no_voice).run()
