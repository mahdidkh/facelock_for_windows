"""
FaceEngine — Core Biometric Pipeline
=====================================
Pipeline:
    Camera Frame
        → MTCNN Face Detection
        → Face Alignment
        → ArcFace Embedding Extraction
        → Cosine Similarity Matching
        → Decision

Models:
    Detection  : MTCNN (mtcnn library)
    Embedding  : ArcFace via InsightFace (buffalo_sc)
"""

import cv2
import numpy as np
import logging
import os
from mtcnn import MTCNN
from insightface.app import FaceAnalysis

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [FaceEngine] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("FaceEngine")


# ── Constants ─────────────────────────────────────────────────────────────────
COSINE_THRESHOLD  = 0.35   # Lower = stricter matching
LIVENESS_ENABLED  = True
MODEL_DIR         = os.path.join(os.path.dirname(__file__), "..", "Models")


class FaceEngine:
    """
    Unified face recognition engine.
    Handles detection, alignment, embedding extraction and matching.
    """

    def __init__(self):
        log.info("Initializing FaceEngine...")

        # ── Face Detector (MTCNN) ─────────────────────────────────────────────
        self.detector = MTCNN()
        log.info("MTCNN detector loaded.")

        # ── ArcFace Embedder (InsightFace) ────────────────────────────────────
        self.embedder = FaceAnalysis(
            name="buffalo_sc",          # lightweight ArcFace model
            root=MODEL_DIR,
            providers=["CPUExecutionProvider"]
        )
        self.embedder.prepare(ctx_id=0, det_size=(640, 640))
        log.info("ArcFace (buffalo_sc) embedder loaded.")

        # ── Liveness Detector ─────────────────────────────────────────────────
        if LIVENESS_ENABLED:
            from FaceService.liveness import LivenessDetector
            self.liveness = LivenessDetector()
            log.info("Liveness detector loaded.")
        else:
            self.liveness = None

        log.info("FaceEngine ready.")

    # ── Public API ────────────────────────────────────────────────────────────

    def extract_embedding(self, frame: np.ndarray):
        """
        From a raw camera frame, detect and embed the face.

        Returns:
            embedding (np.ndarray | None): 512-dim ArcFace vector, or None
            face_box  (dict | None)      : bounding box info, or None
        """
        if frame is None:
            return None, None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Step 1 — Detect face with MTCNN
        detections = self.detector.detect_faces(rgb)
        if not detections:
            log.debug("No face detected.")
            return None, None

        # Pick largest face
        best = max(detections, key=lambda d: d["box"][2] * d["box"][3])
        confidence = best["confidence"]

        if confidence < 0.92:
            log.debug(f"Low detection confidence: {confidence:.2f}")
            return None, None

        # Step 2 — Liveness check
        if self.liveness:
            is_live, reason = self.liveness.check(frame, best)
            if not is_live:
                log.warning(f"Liveness check failed: {reason}")
                return None, None

        # Step 3 — Extract ArcFace embedding via InsightFace
        faces = self.embedder.get(rgb)
        if not faces:
            log.debug("InsightFace found no face for embedding.")
            return None, None

        # Match to MTCNN detection
        embedding = faces[0].embedding
        embedding = self._normalize(embedding)

        log.debug(f"Embedding extracted: {embedding.shape}, conf={confidence:.3f}")
        return embedding, best["box"]

    def match(self, live_embedding: np.ndarray, stored_embedding: np.ndarray) -> tuple[bool, float]:
        """
        Compare live embedding against a stored embedding.

        Returns:
            (authenticated: bool, similarity_score: float)
        """
        if live_embedding is None or stored_embedding is None:
            return False, 0.0

        score = self._cosine_similarity(live_embedding, stored_embedding)
        authenticated = score >= (1.0 - COSINE_THRESHOLD)

        log.info(f"Match score: {score:.4f} | Threshold: {1.0 - COSINE_THRESHOLD:.4f} | Auth: {authenticated}")
        return authenticated, float(score)

    def authenticate_frame(self, frame: np.ndarray, db_manager) -> tuple[str | None, float]:
        """
        Full pipeline: frame → detect → embed → match against ALL users in DB.

        Returns:
            (username | None, best_score)
        """
        embedding, _ = self.extract_embedding(frame)
        if embedding is None:
            return None, 0.0

        users = db_manager.get_all_users()
        if not users:
            log.warning("Database is empty. No users enrolled.")
            return None, 0.0

        best_name  = None
        best_score = 0.0

        for username, stored_emb in users.items():
            authenticated, score = self.match(embedding, stored_emb)
            if authenticated and score > best_score:
                best_score = score
                best_name  = username

        if best_name:
            log.info(f"Authenticated: {best_name} ({best_score:.4f})")
        else:
            log.info(f"No match found. Best score was {best_score:.4f}")

        return best_name, best_score

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
