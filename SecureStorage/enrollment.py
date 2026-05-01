"""
Enrollment Tool — Admin Face Registration
==========================================
Use this tool to register users into the biometric database.

Usage:
    python enrollment.py --enroll  --username "John"
    python enrollment.py --list
    python enrollment.py --delete  --username "John"
    python enrollment.py --test                        (live auth test)
"""

import cv2
import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from FaceService.face_engine import FaceEngine
from SecureStorage.biometric_db import BiometricDatabase

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s"
)
log = logging.getLogger("Enrollment")

CAMERA_INDEX = 0


class EnrollmentTool:

    def __init__(self):
        log.info("Loading face engine and database...")
        self.engine = FaceEngine()
        self.db     = BiometricDatabase()
        self.cap    = None

    # ── Camera ────────────────────────────────────────────────────────────────

    def _open_camera(self):
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def _close_camera(self):
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

    # ── Enrollment ────────────────────────────────────────────────────────────

    def enroll(self, username: str):
        """
        Interactive enrollment:
        - Shows live camera feed
        - User presses SPACE to capture
        - System detects, embeds, and stores face
        """
        print(f"\n{'='*50}")
        print(f"  ENROLLING USER: {username}")
        print(f"{'='*50}")
        print("  Look at the camera and press [SPACE] to capture.")
        print("  Press [Q] to cancel.\n")

        self._open_camera()
        enrolled = False

        while True:
            ret, frame = self.cap.read()
            if not ret:
                log.error("Camera read failed.")
                break

            display = frame.copy()

            # Show live detection status
            embedding, box = self.engine.extract_embedding(frame)

            if box is not None:
                x, y, w, h = box
                cv2.rectangle(display, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(display, "Face detected — Press SPACE",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
            else:
                cv2.putText(display, "No face detected",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)

            cv2.putText(display, f"User: {username}",
                        (10, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
            cv2.imshow("FACELOOK — Enrollment", display)

            key = cv2.waitKey(1) & 0xFF

            if key == ord(" "):      # SPACE = capture
                if embedding is not None:
                    ok = self.db.enroll_user(username, embedding)
                    if ok:
                        print(f"\n  ✅ User '{username}' enrolled successfully!")
                        enrolled = True
                    else:
                        print(f"\n  ❌ Enrollment failed (database error).")
                    break
                else:
                    print("  ⚠ No face detected — please try again.")

            elif key == ord("q"):    # Q = cancel
                print("\n  Enrollment cancelled.")
                break

        self._close_camera()
        return enrolled

    # ── Live Authentication Test ───────────────────────────────────────────────

    def test_auth(self):
        """
        Live authentication test window.
        Shows real-time matching results.
        """
        print(f"\n{'='*50}")
        print("  LIVE AUTHENTICATION TEST")
        print(f"{'='*50}")
        print("  Press [Q] to quit.\n")

        users = self.db.list_users()
        if not users:
            print("  ❌ No users enrolled. Run --enroll first.")
            return

        print(f"  Enrolled users: {[u['username'] for u in users]}\n")
        self._open_camera()

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            display = frame.copy()

            # Flush stale frames
            for _ in range(2):
                self.cap.read()
            ret, frame = self.cap.read()

            name, score = self.engine.authenticate_frame(frame, self.db)

            if name:
                label = f"✅ {name}  ({score:.3f})"
                color = (0, 220, 0)
            elif score > 0:
                label = f"❌ Unknown  ({score:.3f})"
                color = (0, 0, 220)
            else:
                label = "No face detected"
                color = (120, 120, 120)

            cv2.putText(display, label,
                        (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.imshow("FACELOOK — Auth Test", display)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self._close_camera()

    # ── List / Delete ─────────────────────────────────────────────────────────

    def list_users(self):
        users = self.db.list_users()
        if not users:
            print("\n  No users enrolled.")
            return
        print(f"\n  {'Username':<20} {'Enrolled At'}")
        print(f"  {'-'*20} {'-'*25}")
        for u in users:
            print(f"  {u['username']:<20} {u['enrolled_at']}")

    def delete_user(self, username: str):
        confirm = input(f"\n  Delete '{username}'? This cannot be undone. [yes/no]: ")
        if confirm.lower() == "yes":
            ok = self.db.delete_user(username)
            print(f"  {'✅ Deleted.' if ok else '❌ Failed.'}")
        else:
            print("  Cancelled.")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FACELOOK — Biometric Enrollment Tool"
    )
    parser.add_argument("--enroll",   action="store_true", help="Enroll a new user")
    parser.add_argument("--delete",   action="store_true", help="Delete a user")
    parser.add_argument("--list",     action="store_true", help="List all users")
    parser.add_argument("--test",     action="store_true", help="Live auth test")
    parser.add_argument("--username", type=str,            help="Target username")
    args = parser.parse_args()

    tool = EnrollmentTool()

    if args.enroll:
        if not args.username:
            print("Error: --username required for enrollment.")
            sys.exit(1)
        tool.enroll(args.username)

    elif args.delete:
        if not args.username:
            print("Error: --username required for deletion.")
            sys.exit(1)
        tool.delete_user(args.username)

    elif args.list:
        tool.list_users()

    elif args.test:
        tool.test_auth()

    else:
        parser.print_help()
