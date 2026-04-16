import cv2
import time
import os
import getpass # Pour saisir le mot de passe sans l'afficher en clair
import logging
import warnings

# Suppress annoying TensorFlow, oneDNN, and absl warnings/logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
logging.getLogger('tensorflow').setLevel(logging.ERROR)
warnings.filterwarnings('ignore')


from camera_handler import CameraHandler
from face_detector import FaceDetector
from face_encoder import FaceEncoder
from database import DatabaseManager
from face_authenticator import FaceAuthenticator
from system_controller import SystemController

class FaceLockApp:
    def __init__(self):
        self.THRESHOLD = 0.40
        self.GRACE_PERIOD = 3.0    # 3s avant de verrouiller
        self.UNLOCK_CHECK_DELAY = 1.0 # Fréquence de vérification lors du verrouillage
        
        self.camera = CameraHandler()
        self.detector = FaceDetector()
        self.encoder = FaceEncoder(model_path="face_recognition_sface_2021dec.onnx")
        self.db = DatabaseManager()
        self.authenticator = FaceAuthenticator(self.db)
        self.controller = SystemController()
        
        self.is_locked = False
        self.windows_password = ""

    def run_enrollment(self):
        """Mode Enregistrement."""
        if not self.camera.start(): return
        print("\n=== REGARDEZ LA CAMERA ET APPUYEZ SUR 's' ===")
        while True:
            frame = self.camera.capture_frame()
            if frame is None: break
            face_data = self.detector.detect_face(frame)
            if face_data:
                a = face_data['facial_area']
                cv2.rectangle(frame, (a['x'], a['y']), (a['x']+a['w'], a['y']+a['h']), (0, 255, 0), 2)
            cv2.imshow("Enrollment", frame)
            key = cv2.waitKey(1)
            if key == ord('s') and face_data:
                face_img = self.detector.align_face(frame, face_data)
                embedding = self.encoder.generate_embedding(face_img)
                name = input("Nom d'utilisateur : ")
                self.authenticator.register_new_user(name, embedding)
                break
            elif key == ord('q'): break
        self.camera.stop()
        cv2.destroyAllWindows()

    def run_protection_loop(self):
        """Mode Protection avec Verrouillage/Déverrouillage."""
        # 1. On demande le mot de passe une seule fois au début
        print("\n[SECURITE] Veuillez entrer votre mot de passe/PIN Windows pour l'auto-unlock.")
        self.windows_password = getpass.getpass("Mot de passe Windows : ")
        
        print("\n[INFO] PROTECTION ACTIVÉE. Appuyez sur 'q' pour arrêter.")
        if not self.camera.start(): return
        
        last_seen_time = time.time()
        
        try:
            while True:
                frame = self.camera.capture_frame()
                if frame is None:
                    # Sous Windows, la caméra peut parfois être coupée si verrouillé
                    time.sleep(self.UNLOCK_CHECK_DELAY)
                    continue

                face_data = self.detector.detect_face(frame)
                is_authorized = False
                
                if face_data:
                    face_img = self.detector.align_face(frame, face_data)
                    embedding = self.encoder.generate_embedding(face_img)
                    name, score = self.authenticator.authenticate(embedding, threshold=self.THRESHOLD)
                    
                    if name:
                        is_authorized = True
                        last_seen_time = time.time()
                        
                        # SI RECONNU ET VERROUILLÉ -> ON DÉVERROUILLE
                        if self.is_locked:
                            print(f"[BONJOUR] {name} reconnu ! Déverrouillage...")
                            self.controller.unlock_windows(self.windows_password)
                            self.is_locked = False
                            # Temps pour laisser Windows s'ouvrir avant de reprendre
                            time.sleep(2.0)
                        else:
                            self.controller.keep_awake()

                # SI ABSENT TROP LONGTEMPS -> ON VERROUILLE
                elapsed = time.time() - last_seen_time
                if not is_authorized and elapsed > self.GRACE_PERIOD and not self.is_locked:
                    print(f"[ALERTE] Absence détectée ({elapsed:.1f}s) ! Verrouillage...")
                    self.controller.lock_windows()
                    self.is_locked = True
                
                # Feedback console/UI
                if not self.is_locked:
                    status = "OK" if is_authorized else f"ABSENT ({elapsed:.1f}s)"
                    cv2.putText(frame, f"Statut: {status}", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0) if is_authorized else (0,0,255), 2)
                    cv2.imshow("FaceLock Active", frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            print("\nArrêt demandé.")
            
        self.camera.stop()
        cv2.destroyAllWindows()
        self.controller.reset_sleep_timer()

if __name__ == "__main__":
    app = FaceLockApp()
    print("\n--- BIENVENUE SUR FACELOCK AVANCÉ ---")
    print("1. S'enregistrer (Enroll)")
    print("2. Lancer la PROTECTION (Auto Lock/Unlock)")
    print("3. Quitter")
    choice = input("\nChoix (1-3) : ")
    if choice == "1": app.run_enrollment()
    elif choice == "2": app.run_protection_loop()
