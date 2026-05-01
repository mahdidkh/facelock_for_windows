"""
Named Pipe Server — IPC Bridge
================================
Listens on a Windows Named Pipe for commands from CredentialProvider.dll.

Protocol (JSON over pipe):
    Request  → {"command": "authenticate"}
    Response ← {"success": true, "username": "John", "score": 0.97}

    Request  → {"command": "enroll", "username": "John"}
    Response ← {"success": true}

    Request  → {"command": "ping"}
    Response ← {"success": true, "message": "pong"}

Security:
    - Pipe access restricted to LOCAL SYSTEM and Administrators only
    - All communication is local (no network)
"""

import win32pipe
import win32file
import win32security
import pywintypes
import json
import logging
import threading
import cv2
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from FaceService.face_engine import FaceEngine
from SecureStorage.biometric_db import BiometricDatabase

log = logging.getLogger("PipeServer")

PIPE_NAME    = r"\\.\pipe\FacelookBiometric"
BUFFER_SIZE  = 65536
CAMERA_INDEX = 0


class PipeServer:
    """
    Listens on a Named Pipe and handles biometric requests
    from the C++ Credential Provider DLL.
    """

    def __init__(self):
        self.engine  = FaceEngine()
        self.db      = BiometricDatabase()
        self.running = False
        self.camera  = None
        log.info("PipeServer initialized.")

    # ── Server Lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Start listening on the Named Pipe (blocking loop)."""
        self.running = True
        self._open_camera()
        log.info(f"Listening on {PIPE_NAME}")

        while self.running:
            try:
                pipe = self._create_pipe()
                log.info("Waiting for client connection...")

                win32pipe.ConnectNamedPipe(pipe, None)
                log.info("Client connected.")

                # Handle each client in a thread
                t = threading.Thread(
                    target=self._handle_client,
                    args=(pipe,),
                    daemon=True
                )
                t.start()

            except pywintypes.error as e:
                if self.running:
                    log.error(f"Pipe error: {e}")

    def stop(self):
        self.running = False
        self._close_camera()
        log.info("PipeServer stopped.")

    # ── Request Handling ──────────────────────────────────────────────────────

    def _handle_client(self, pipe):
        """Read a request, process it, send response, close connection."""
        try:
            # Read request
            result, raw = win32file.ReadFile(pipe, BUFFER_SIZE)
            request = json.loads(raw.decode("utf-8"))
            log.info(f"Request received: {request}")

            # Dispatch command
            command  = request.get("command", "")
            response = self._dispatch(command, request)

            # Send response
            payload = json.dumps(response).encode("utf-8")
            win32file.WriteFile(pipe, payload)
            log.info(f"Response sent: {response}")

        except Exception as e:
            log.error(f"Client handler error: {e}")
            try:
                error_resp = json.dumps({"success": False, "error": str(e)}).encode()
                win32file.WriteFile(pipe, error_resp)
            except Exception:
                pass
        finally:
            win32file.CloseHandle(pipe)

    def _dispatch(self, command: str, request: dict) -> dict:
        """Route command to correct handler."""
        if command == "ping":
            return {"success": True, "message": "pong"}

        elif command == "authenticate":
            return self._cmd_authenticate()

        elif command == "enroll":
            username = request.get("username", "").strip()
            if not username:
                return {"success": False, "error": "Missing username"}
            return self._cmd_enroll(username)

        elif command == "list_users":
            return {"success": True, "users": self.db.list_users()}

        elif command == "delete_user":
            username = request.get("username", "").strip()
            ok = self.db.delete_user(username)
            return {"success": ok}

        else:
            return {"success": False, "error": f"Unknown command: {command}"}

    # ── Commands ──────────────────────────────────────────────────────────────

    def _cmd_authenticate(self) -> dict:
        """
        Capture a frame, run full face recognition pipeline,
        return match result to the Credential Provider.
        """
        frame = self._capture_frame()
        if frame is None:
            return {"success": False, "error": "Camera unavailable"}

        username, score = self.engine.authenticate_frame(frame, self.db)

        if username:
            self.db.log_auth_attempt(username, success=True, score=score)
            return {
                "success"  : True,
                "username" : username,
                "score"    : round(score, 4)
            }
        else:
            self.db.log_auth_attempt(None, success=False, score=score)
            return {
                "success" : False,
                "score"   : round(score, 4),
                "error"   : "Face not recognized"
            }

    def _cmd_enroll(self, username: str) -> dict:
        """
        Capture a frame, extract embedding, enroll the user.
        Used by the admin enrollment tool.
        """
        frame = self._capture_frame()
        if frame is None:
            return {"success": False, "error": "Camera unavailable"}

        embedding, box = self.engine.extract_embedding(frame)
        if embedding is None:
            return {"success": False, "error": "No face detected during enrollment"}

        ok = self.db.enroll_user(username, embedding)
        return {"success": ok, "username": username}

    # ── Camera ────────────────────────────────────────────────────────────────

    def _open_camera(self):
        self.camera = cv2.VideoCapture(CAMERA_INDEX)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.camera.isOpened():
            log.error("Failed to open camera!")
        else:
            log.info(f"Camera {CAMERA_INDEX} opened.")

    def _close_camera(self):
        if self.camera:
            self.camera.release()
            log.info("Camera released.")

    def _capture_frame(self) -> np.ndarray | None:
        """Capture a single frame from the camera."""
        if not self.camera or not self.camera.isOpened():
            return None
        # Discard stale frames (flush buffer)
        for _ in range(3):
            self.camera.read()
        ret, frame = self.camera.read()
        return frame if ret else None

    # ── Named Pipe Creation ───────────────────────────────────────────────────

    @staticmethod
    def _create_pipe():
        """
        Create a Named Pipe with restricted security:
        Only LOCAL SYSTEM and Administrators can connect.
        """
        # Build a security descriptor
        sd = win32security.SECURITY_DESCRIPTOR()
        sa = win32security.SECURITY_ATTRIBUTES()

        # Allow SYSTEM and Admins full access
        dacl = win32security.ACL()
        system_sid = win32security.CreateWellKnownSid(
            win32security.WinLocalSystemSid, None
        )
        admins_sid = win32security.CreateWellKnownSid(
            win32security.WinBuiltinAdministratorsSid, None
        )
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            system_sid
        )
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            admins_sid
        )
        sd.SetSecurityDescriptorDacl(True, dacl, False)
        sa.SECURITY_DESCRIPTOR = sd

        pipe = win32pipe.CreateNamedPipe(
            PIPE_NAME,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            BUFFER_SIZE,
            BUFFER_SIZE,
            5000,    # 5 second timeout
            sa
        )
        return pipe


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    server = PipeServer()
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
