"""
FaceRecognitionService — Windows Service Entry Point
======================================================
Wraps the PipeServer as a proper Windows Service.

Install:  python service_main.py install
Start:    python service_main.py start
Stop:     python service_main.py stop
Remove:   python service_main.py remove

Or via SC:
    sc start FacelookBiometricService
    sc stop  FacelookBiometricService
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import logging
import sys
import os
import threading

# Ensure parent directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from FaceService.pipe_server import PipeServer


# ── Log to Windows Event Log ──────────────────────────────────────────────────
LOG_DIR  = os.path.join(os.path.dirname(__file__), "..", "Logs")
LOG_FILE = os.path.join(LOG_DIR, "facelook_service.log")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("FacelookService")


class FacelookBiometricService(win32serviceutil.ServiceFramework):
    """
    Windows Service that hosts the Face Recognition engine.
    Communicates with CredentialProvider.dll via Named Pipe.
    """

    _svc_name_         = "FacelookBiometricService"
    _svc_display_name_ = "Facelook Biometric Recognition Service"
    _svc_description_  = (
        "Hosts the face recognition AI pipeline for FACELOOK. "
        "Provides biometric authentication to the Windows Credential Provider "
        "via a secure Named Pipe."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event  = win32event.CreateEvent(None, 0, 0, None)
        self.pipe_server = None
        self.server_thread = None

    # ── Service Control ───────────────────────────────────────────────────────

    def SvcStop(self):
        """Called by Windows SCM to stop the service."""
        log.info("Stop signal received from SCM.")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

        if self.pipe_server:
            self.pipe_server.stop()

    def SvcDoRun(self):
        """Main service execution."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, "")
        )
        log.info("FacelookBiometricService starting...")
        self._run()

    # ── Main Logic ────────────────────────────────────────────────────────────

    def _run(self):
        """Initialize the pipe server and wait for stop signal."""
        try:
            self.pipe_server   = PipeServer()
            self.server_thread = threading.Thread(
                target=self.pipe_server.start,
                daemon=True
            )
            self.server_thread.start()
            log.info("Named Pipe server started in background thread.")

            # Block here until SCM sends stop signal
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

        except Exception as e:
            log.critical(f"Service crashed: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"FacelookService error: {e}")
        finally:
            log.info("FacelookBiometricService stopped.")


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Called by SCM directly
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(FacelookBiometricService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Called from command line: install / start / stop / remove
        win32serviceutil.HandleCommandLine(FacelookBiometricService)
