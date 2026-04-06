# RYDI Assistant — Contrôle vocal complet

Face ID → Déverrouillage → Contrôle vocal total de ta machine.

---

## Installation

```
install.bat
```
Installe : `opencv-contrib-python Pillow SpeechRecognition pyttsx3 pyaudio pyautogui`

---

## Régler le problème "Inconnu"

**C'est la première chose à faire :**

```bash
python calibrate.py
```

Il affiche quelque chose comme :
```
✅ Seuil recommandé : 108
→ Dans config.json : "threshold": 108
```

Ouvre `config.json` → change `"threshold": 95` par la valeur suggérée.

---

## Lancement

```bash
python assistant.py              # Normal
python assistant.py --no-face    # Sans Face ID (debug)
python assistant.py --camera 1   # Autre webcam
```

---

## Configurer tes apps — config.json

Ouvre `config.json` et adapte les chemins à ta machine :

```json
"apps": {
    "chrome":  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "vscode":  "C:\\Users\\DELL\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
    "spotify": "C:\\Users\\DELL\\AppData\\Roaming\\Spotify\\Spotify.exe"
}
```

Pour trouver le chemin d'une app :
- Clic droit sur le raccourci → Propriétés → Cible

Et tes scripts Python dans :
```json
"scripts": {
    "astrawatch": "C:\\RYDI\\AstraWatch\\app.py",
    "mon_projet": "C:\\Users\\DELL\\monscript.py"
}
```

---

## Ajouter tes propres commandes — commands.json

```json
"apps": {
    "ouvre mon projet": {"action": "open_app", "target": "mon_projet"}
}
```

Ajoute autant de commandes que tu veux.

---

## Toutes les commandes vocales

### Applications
```
"ouvre chrome"          → lance Chrome
"ouvre vscode"          → lance VSCode  
"ouvre spotify"         → lance Spotify
"ouvre le terminal"     → lance cmd
"ferme cette fenêtre"   → Alt+F4
"minimise"              → réduit la fenêtre
"agrandis"              → plein écran
```

### Musique
```
"play" / "pause"        → lecture/pause
"suivant"               → chanson suivante
"précédent"             → chanson précédente
"volume plus"           → monte le volume
"volume moins"          → baisse le volume
"coupe le son"          → mute
```

### Dictée (dans n'importe quelle app)
```
"écris bonjour monde"   → tape "bonjour monde" là où le curseur est
"tape mon email"        → tape "mon email"
"arrête d'écrire"       → arrête la dictée
```

### Fichiers
```
"ouvre mes documents"   → ouvre Documents
"ouvre le bureau"       → ouvre Desktop
"ouvre les téléchargements"
"ouvre mes projets"     → ouvre C:\RYDI (configurable)
```

### Scripts Python
```
"lance astrawatch"      → python C:\RYDI\AstraWatch\app.py
"lance le serveur"      → python C:\RYDI\server\app.py
"exécute le test"       → python C:\RYDI\tests\run_tests.py
```

### Système
```
"capture d'écran"       → screenshot sauvegardé dans screenshots/
"copie"                 → Ctrl+C
"colle"                 → Ctrl+V
"annule"                → Ctrl+Z
"sauvegarde"            → Ctrl+S
"tout sélectionner"     → Ctrl+A
"cherche"               → Ctrl+F
"verrouille"            → Win+L
"éteins le pc"          → shutdown /s /t 5
"redémarre"             → shutdown /r /t 5
```

### Web
```
"recherche météo Douala"    → Google search
"ouvre youtube"             → youtube.com
"ouvre github"              → github.com
"ouvre gmail"               → gmail.com
```

---

## Démarrage automatique

`Win + R` → `shell:startup` → copie `start_assistant.bat`

Crée `start_assistant.bat` dans le projet :
```bat
@echo off
cd /d "C:\CHEMIN\rydi_assistant"
python assistant.py
```

---

## Architecture

```
Face ID (webcam)
   ↓ Confirmé (8 frames)
Déverrouillé
   ↓
Écoute micro en continu
   ↓
Reconnaissance Google Speech (fr-FR)
   ↓
CommandEngine → action OS
```

---

*RYDI Group*
