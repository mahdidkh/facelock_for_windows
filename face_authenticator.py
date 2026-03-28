import numpy as np
from database import DatabaseManager

class FaceAuthenticator:
    """
    Module de Comparaison (Version SQLite) :
    Utilise la base de données structurée pour charger les identités 
    et compare les signatures biométriques.
    """

    def __init__(self, db_manager):
        self.db = db_manager
        # On charge les signatures depuis la DB SQLite au démarrage
        self.authorized_users = self.db.get_all_users()

    def refresh_identities(self):
        """Recharge les utilisateurs depuis la base de données."""
        self.authorized_users = self.db.get_all_users()

    def register_new_user(self, name, embedding):
        """Enregistre un nouvel utilisateur via la DB."""
        if self.db.add_user(name, embedding):
            self.refresh_identities()
            return True
        return False

    def authenticate(self, current_embedding, threshold=0.363):
        """
        Compare un nouveau visage avec la base de données SQLite.
        Retourne (Nom reconnu, Score).
        """
        if not self.authorized_users or current_embedding is None:
            return None, 0.0

        best_match_name = None
        max_similarity = -1.0

        for name, saved_embedding in self.authorized_users.items():
            # Similarité Cosinus
            similarity = np.dot(current_embedding, saved_embedding) / (
                np.linalg.norm(current_embedding) * np.linalg.norm(saved_embedding)
            )

            if similarity > max_similarity:
                max_similarity = similarity
                best_match_name = name

        # Vérification du seuil (Threshold)
        if max_similarity >= threshold:
            return best_match_name, max_similarity
        
        return None, max_similarity
