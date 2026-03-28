import sqlite3
import numpy as np
import io
import os

class DatabaseManager:
    """
    Module de Gestion de la Base de Données (Version SQLite) :
    Remplace les fichiers pickle par une base de données structurée 
    pour plus de sécurité et de robustesse.
    """

    def __init__(self, db_name="facelock_vault.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Crée la table des utilisateurs autorisés si elle n'existe pas."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authorized_faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                embedding BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def adapt_array(self, arr):
        """Transforme un tableau NumPy en format binaire BLOB."""
        out = io.BytesIO()
        np.save(out, arr)
        out.seek(0)
        return sqlite3.Binary(out.read())

    def convert_array(self, text):
        """Transforme un BLOB binaire en tableau NumPy utilisable."""
        out = io.BytesIO(text)
        out.seek(0)
        return np.load(out)

    def add_user(self, username, embedding):
        """Enregistre un nouvel utilisateur avec son vecteur biométrique."""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            blob_data = self.adapt_array(embedding)
            cursor.execute(
                "INSERT OR REPLACE INTO authorized_faces (username, embedding) VALUES (?, ?)",
                (username, blob_data)
            )
            conn.commit()
            conn.close()
            print(f"[SUCCESS] Utilisateur {username} enregistré dans la base de données.")
            return True
        except Exception as e:
            print(f"[ERREUR DB] {e}")
            return False

    def get_all_users(self):
        """Récupère tous les utilisateurs et leurs embeddings pour la comparaison."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT username, embedding FROM authorized_faces")
        rows = cursor.fetchall()
        
        users_dict = {}
        for row in rows:
            username = row[0]
            embedding = self.convert_array(row[1])
            users_dict[username] = embedding
            
        conn.close()
        return users_dict

if __name__ == "__main__":
    # Test flash du module
    db = DatabaseManager()
    
    # Création d'une signature test (128 dimensions pour SFace)
    test_emb = np.random.rand(128)
    db.add_user("Admin_Secure", test_emb)
    
    # Vérification de la lecture
    identities = db.get_all_users()
    if "Admin_Secure" in identities:
        print(f"✅ Utilisateur Admin_Secure trouvé dans la DB SQLite.")
        print(f"✅ Taille de sa signature : {len(identities['Admin_Secure'])} dimensions.")
