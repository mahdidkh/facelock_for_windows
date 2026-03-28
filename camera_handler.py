import cv2
import numpy as np
from deepface import DeepFace
import logging

# On désactive les logs verbeux de TensorFlow pour que ce soit plus propre
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

class CameraHandler:
    """
    Module d'Acquisition (Version DeepFace) : Gère le flux vidéo, 
    la détection initiale et l'analyse de luminosité sans conflits.
    """

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.cap = None
        # On utilise le backend 'opencv' ou 'ssd' pour la vitesse
        self.detector_backend = 'opencv' 

    def start(self):
        """Démarre la webcam."""
        if self.cap is None:
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
        if not self.cap.isOpened():
            self.cap = None
            return False
        return True

    def stop(self):
        """Libère les ressources."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def capture_frame(self):
        """Récupère une frame de la webcam."""
        if self.cap is None or not self.cap.isOpened():
            if not self.start():
                return None
        
        success, frame = self.cap.read()
        if not success:
            return None
            
        # Effet miroir
        frame = cv2.flip(frame, 1)
        return frame

    def detect_face_and_light(self, frame):
        """
        Détecte le visage via DeepFace et analyse la luminosité.
        Retourne (is_ok, score, face_info)
        """
        if frame is None:
            return False, 0, None

        try:
            # Extraction rapide du visage
            faces = DeepFace.extract_faces(
                img_path=frame, 
                detector_backend=self.detector_backend,
                enforce_detection=False
            )
            
            face_info = None
            target_region = frame

            if len(faces) > 0 and faces[0]['confidence'] > 0.5:
                face_info = faces[0]
                area = face_info['facial_area']
                # Crop pour analyse de lumière sur le visage
                target_region = frame[area['y']:area['y']+area['h'], area['x']:area['x']+area['w']]

            gray = cv2.cvtColor(target_region, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            
            is_ok = (50 <= brightness <= 220)
            return is_ok, brightness, face_info

        except Exception as e:
            return False, 0, None

if __name__ == "__main__":
    handler = CameraHandler()
    if handler.start():
        print("[INFO] Moteur DeepFace prêt. Appuyez sur 'q' pour quitter.")
        while True:
            frame = handler.capture_frame()
            if frame is not None:
                is_ok, score, face = handler.detect_face_and_light(frame)
                
                # Feedback visuel
                color = (0, 255, 0) if is_ok else (0, 0, 255)
                
                if face:
                    a = face['facial_area']
                    cv2.rectangle(frame, (a['x'], a['y']), (a['x']+a['w'], a['y']+a['h']), color, 2)
                    
                cv2.putText(frame, f"Lumiere: {int(score)} {'OK' if is_ok else 'BAD'}", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                cv2.imshow("FaceLock Acquisition - DeepFace", frame)
                
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        handler.stop()
        cv2.destroyAllWindows()
