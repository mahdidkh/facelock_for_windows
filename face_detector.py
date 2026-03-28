import cv2
import numpy as np
from deepface import DeepFace
import os

# Désactivation des messages d'initialisation de TensorFlow
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

class FaceDetector:
    """
    Module de Détection et d'Alignement (Version DeepFace-SSD) :
    Remplace MediaPipe pour éviter les conflits de bibliothèques.
    Détecte et aligne le visage pour la reconnaissance.
    """

    def __init__(self, detector_backend='opencv'):
        # 'opencv' est très rapide, 'ssd' est plus précis mais plus lourd.
        self.detector_backend = detector_backend

    def detect_face(self, frame):
        """
        Détecte le visage et retourne les informations (bbox, points clés).
        """
        if frame is None:
            return None

        try:
            # On utilise extract_faces pour obtenir la détection et l'alignement d'un coup
            faces = DeepFace.extract_faces(
                img_path=frame, 
                detector_backend=self.detector_backend,
                enforce_detection=False,
                align=True # Active l'alignement automatique (yeux horizontaux)
            )
            
            # On ne garde que les détections avec une bonne confiance
            valid_faces = [f for f in faces if f['confidence'] > 0.4]
            return valid_faces[0] if valid_faces else None
            
        except Exception:
            return None

    def align_face(self, frame, face_data):
        """
        Récupère l'image du visage déjà alignée par DeepFace.
        """
        if face_data is None:
            return None
        
        # DeepFace fournit directement le visage aligné et normalisé (0-1)
        face_img = face_data['face']
        
        # Conversion en format standard 0-255 uint8 pour OpenCV et affichage
        face_img = (face_img * 255).astype(np.uint8)
        
        # Redimensionnement standard 224x224
        aligned_face = cv2.resize(face_img, (224, 224))
        
        # Le visage de DeepFace est en RGB, on le remet en BGR pour OpenCV
        return cv2.cvtColor(aligned_face, cv2.COLOR_RGB2BGR)

if __name__ == "__main__":
    from camera_handler import CameraHandler
    
    detector = FaceDetector()
    handler = CameraHandler()
    
    if handler.start():
        print("[INFO] Test du module Détecteur (Moteur DeepFace). Appuyez sur 'q' pour quitter.")
        while True:
            frame = handler.capture_frame()
            if frame is not None:
                face_data = detector.detect_face(frame)
                
                if face_data:
                    # Affichage du visage aligné
                    face = detector.align_face(frame, face_data)
                    if face is not None:
                        cv2.imshow("Visage Aligne (DeepFace)", face)
                    
                    # Dessiner le rectangle sur la vue principale
                    a = face_data['facial_area']
                    cv2.rectangle(frame, (a['x'], a['y']), (a['x']+a['w'], a['y']+a['h']), (0, 255, 0), 2)
                
                cv2.imshow("Main View", frame)
                
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        handler.stop()
        cv2.destroyAllWindows()
