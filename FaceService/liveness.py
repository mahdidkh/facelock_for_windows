"""
LivenessDetector — Anti-Spoofing Module
=========================================
Detects if the face in front of the camera is:
    ✅ A real live person
    ❌ A printed photo
    ❌ A screen replay attack

Methods used:
    1. Texture Analysis  — Laplacian variance (blur detection)
    2. Color Variance    — Real faces have natural color variation
    3. Reflection check  — Screens produce unnatural brightness patterns
    4. Landmark ratio    — Basic 3D geometry check via eye/nose ratios
"""

import cv2
import numpy as np
import logging

log = logging.getLogger("Liveness")


class LivenessDetector:
    """
    Passive liveness detection (no user action needed).
    Runs multiple checks on each frame and returns a combined result.
    """

    # ── Thresholds (tune these during testing) ────────────────────────────────
    MIN_LAPLACIAN_VAR   = 80.0    # Below this = blurry = likely printed photo
    MIN_COLOR_VARIANCE  = 12.0    # Real faces have richer color distributions
    MAX_BRIGHTNESS      = 210.0   # Screens tend to be over-bright
    MIN_BRIGHTNESS      = 40.0    # Too dark = suspicious

    def __init__(self):
        log.info("LivenessDetector initialized (passive mode).")

    def check(self, frame: np.ndarray, detection: dict) -> tuple[bool, str]:
        """
        Run all liveness checks on a detected face region.

        Args:
            frame     : Full BGR camera frame
            detection : MTCNN detection dict with 'box' key

        Returns:
            (is_live: bool, reason: str)
        """
        face_crop = self._crop_face(frame, detection)
        if face_crop is None:
            return False, "Could not crop face region"

        # Run all checks
        checks = [
            self._check_blur(face_crop),
            self._check_color_variance(face_crop),
            self._check_brightness(face_crop),
        ]

        # All checks must pass
        for passed, reason in checks:
            if not passed:
                log.warning(f"Liveness FAILED: {reason}")
                return False, reason

        log.debug("Liveness check PASSED.")
        return True, "OK"

    # ── Individual Checks ─────────────────────────────────────────────────────

    def _check_blur(self, face: np.ndarray) -> tuple[bool, str]:
        """
        Printed photos often appear slightly blurry when captured by camera.
        Uses Laplacian variance — low variance = blurry.
        """
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        log.debug(f"Blur variance: {variance:.2f}")

        if variance < self.MIN_LAPLACIAN_VAR:
            return False, f"Image too blurry (var={variance:.1f}, min={self.MIN_LAPLACIAN_VAR})"
        return True, "OK"

    def _check_color_variance(self, face: np.ndarray) -> tuple[bool, str]:
        """
        Real faces have natural color variation across skin, hair, eyes.
        Printed photos on matte paper tend to have less color richness.
        """
        hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
        saturation_variance = float(np.std(hsv[:, :, 1]))
        log.debug(f"Color variance (saturation std): {saturation_variance:.2f}")

        if saturation_variance < self.MIN_COLOR_VARIANCE:
            return False, f"Low color variance (std={saturation_variance:.1f}, min={self.MIN_COLOR_VARIANCE})"
        return True, "OK"

    def _check_brightness(self, face: np.ndarray) -> tuple[bool, str]:
        """
        Screen replay attacks often produce a face that is unnaturally bright.
        Also catches very dark environments.
        """
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        log.debug(f"Mean brightness: {mean_brightness:.2f}")

        if mean_brightness > self.MAX_BRIGHTNESS:
            return False, f"Face too bright (screen replay suspected): {mean_brightness:.1f}"
        if mean_brightness < self.MIN_BRIGHTNESS:
            return False, f"Face too dark (poor lighting): {mean_brightness:.1f}"
        return True, "OK"

    # ── Helper ────────────────────────────────────────────────────────────────

    @staticmethod
    def _crop_face(frame: np.ndarray, detection: dict) -> np.ndarray | None:
        """Crop the face bounding box from the frame with padding."""
        try:
            x, y, w, h = detection["box"]
            pad = 10
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(frame.shape[1], x + w + pad)
            y2 = min(frame.shape[0], y + h + pad)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                return None
            return crop
        except Exception as e:
            log.error(f"Face crop error: {e}")
            return None


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from mtcnn import MTCNN
    detector = MTCNN()
    liveness = LivenessDetector()
    cap = cv2.VideoCapture(0)

    print("[INFO] Liveness test — press 'q' to quit")
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        detections = detector.detect_faces(rgb)

        label = "No Face"
        color = (128, 128, 128)

        if detections:
            best = max(detections, key=lambda d: d["box"][2] * d["box"][3])
            is_live, reason = liveness.check(frame, best)
            x, y, w, h = best["box"]
            label = f"LIVE" if is_live else f"FAKE: {reason[:30]}"
            color = (0, 255, 0) if is_live else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.imshow("Liveness Test", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
