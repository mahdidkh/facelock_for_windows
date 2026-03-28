import os
import ctypes
import time
import pydirectinput # Meilleur que pyautogui pour le contournement Windows
import pyautogui # Support pour la frappe de texte

class SystemController:
    """
    Module de Contrôle Système (Avancé) :
    Peut verrouiller et tenter de déverrouiller la session Windows.
    """

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def lock_windows(self):
        """Verrouillage natif de Windows."""
        print("[CONTROL] Verrouillage Windows (Win+L)...")
        self.user32.LockWorkStation()

    def unlock_windows(self, password):
        """
        Tente de déverrouiller la session en simulant la saisie du mot de passe.
        Note: Nécessite parfois des droits administratifs sur certaines versions de Windows.
        """
        print("[CONTROL] Tentative de déverrouillage automatique...")
        
        # 1. On "réveille" l'écran de verrouillage avec une touche
        pyautogui.press('enter')
        time.sleep(1.0) # On laisse l'animation se finir
        
        # 2. On tape le mot de passe
        pyautogui.write(password, interval=0.1)
        
        # 3. On valide
        pyautogui.press('enter')
        print("[SUCCESS] Commande de déverrouillage envoyée.")

    def keep_awake(self):
        self.kernel32.SetThreadExecutionState(0x80000001 | 0x00000002)

    def reset_sleep_timer(self):
        self.kernel32.SetThreadExecutionState(0x80000000)

if __name__ == "__main__":
    # Test (Pensez à bien avoir votre mot de passe pour tester !)
    ctrl = SystemController()
    input("Prêt pour le test ? Verrouillage puis déverrouillage automatique dans 5s... (Appuyez sur Entrée)")
    
    ctrl.lock_windows()
    time.sleep(5)
    
    # Remplacer 'VOTRE_PWD' par votre vrai code pour le test local
    ctrl.unlock_windows('VOTRE_PWD')
