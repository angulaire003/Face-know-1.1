"""
calibrate.py — RYDI Assistant
Teste le seuil LBPH sur tes photos existantes pour trouver
la valeur optimale. Lance AVANT main.py si tu as "Inconnu".

Usage:
    python calibrate.py
"""

import cv2
import os
import numpy as np

MODEL_PATH  = os.path.join("models", "face_model.yml")
LABELS_PATH = os.path.join("models", "labels.txt")
KNOWN_DIR   = "known_faces"

def load_labels():
    labels = {}
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH) as f:
            for line in f:
                if ":" in line:
                    i, n = line.strip().split(":", 1)
                    labels[int(i)] = n
    return labels

def main():
    if not os.path.exists(MODEL_PATH):
        print("❌ Modèle introuvable. Lance train.py d'abord.")
        return

    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.read(MODEL_PATH)
    labels   = load_labels()
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))

    confidences = []
    print("\n🔍 Test sur tes photos d'entraînement...\n")

    for person in os.listdir(KNOWN_DIR):
        person_dir = os.path.join(KNOWN_DIR, person)
        if not os.path.isdir(person_dir):
            continue
        imgs = [f for f in os.listdir(person_dir)
                if f.lower().endswith((".jpg",".png",".jpeg"))]
        # Tester sur 15 photos max
        for fname in imgs[:15]:
            img = cv2.imread(os.path.join(person_dir, fname),
                             cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            img = cv2.resize(img, (160, 160))
            img = clahe.apply(img)
            label_id, conf = rec.predict(img)
            confidences.append((person, labels.get(label_id,"?"), conf))

    if not confidences:
        print("❌ Aucune image testée.")
        return

    confs = [c[2] for c in confidences]
    print(f"{'Photo de':<15} {'Prédit':<15} {'Confidence':>12}")
    print("-" * 44)
    for person, predicted, conf in confidences[:20]:
        match = "✅" if person == predicted else "❌"
        print(f"{person:<15} {predicted:<15} {conf:>10.1f}  {match}")

    print(f"\n📊 Statistiques :")
    print(f"   Min  : {min(confs):.1f}")
    print(f"   Max  : {max(confs):.1f}")
    print(f"   Moy  : {np.mean(confs):.1f}")
    print(f"   Méd  : {np.median(confs):.1f}")

    suggested = np.percentile(confs, 85) + 10
    print(f"\n✅ Seuil recommandé : {suggested:.0f}")
    print(f"\n   → Dans train.py  : threshold={suggested:.0f}")
    print(f"   → Dans main.py   : THRESHOLD = {suggested:.0f}")
    print(f"\n   Règle : si 'Inconnu' → monte le seuil (+10)")
    print(f"           si faux positifs → baisse (-10)\n")

if __name__ == "__main__":
    main()
