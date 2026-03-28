import cv2
import numpy as np
import os

class FaceEncoder:
    """
    Module d'Extraction de Caractéristiques (Version SFace OpenCV) :
    Utilise le modèle SFace (très robuste et léger) pour transformer 
    le visage en un vecteur numérique de 128 dimensions.
    """

    def __init__(self, model_path="face_recognition_sface_2021dec.onnx"):
        self.model_path = model_path
        if not os.path.exists(self.model_path):
            print(f"[ERREUR] Le fichier {self.model_path} est introuvable !")
            self.model = None
        else:
            # On charge le modèle SFace de l'OpenCV Zoo
            self.model = cv2.FaceRecognizerSF.create(self.model_path, "")

    def generate_embedding(self, face_img):
        """
        Génère l'embedding du visage.
        Note: SFace prend en entrée le visage déjà aligné (112x112 suggéré).
        """
        if self.model is None or face_img is None:
            return None

        try:
            # SFace préfère les images 112x112
            face_resized = cv2.resize(face_img, (112, 112))
            
            # Calcul de l'embedding (vecteur caractéristique)
            embedding = self.model.feature(face_resized)
            
            # On normalise pour assurer une comparaison stable
            return embedding.flatten()
            
        except Exception as e:
            print(f"[ERREUR Encoder] {e}")
            return None

if __name__ == "__main__":
    # Test unitaire rapide
    from face_detector import FaceDetector
    from camera_handler import CameraHandler
    
    handler = CameraHandler()
    detector = FaceDetector()
    encoder = FaceEncoder()
    
    if handler.start():
        print("[INFO] Scanner un visage pour générer un embedding SFace...")
        print("[INFO] Appuyez sur 'q' pour quitter.")
        while True:
            frame = handler.capture_frame()
            if frame is not None:
                face_data = detector.detect_face(frame)
                
                if face_data:
                    # Le detector aligne déjà le visage
                    face_img = detector.align_face(frame, face_data)
                    embedding = encoder.generate_embedding(face_img)
                    
                    if embedding is not None:
                        print(f"✅ Embedding SFace généré ({len(embedding)} dimensions)")
                        print(f"Premières valeurs : {embedding[:5]}...")
                        # Ne pas s'arrêter tout de suite pour voir le flux
                
                cv2.imshow("Test SFace Encoder", frame)
                
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        handler.stop()
        cv2.destroyAllWindows()
