"""Transcription vocale locale avec faster-whisper (https://github.com/SYSTRAN/faster-whisper).

Optionnel : si faster-whisper n'est pas installé, l'API renvoie 503 et le frontend
se rabat sur la dictée du navigateur.

Le modèle est téléchargé au premier usage dans ./models/whisper. Pour le faire à l'avance :
    python -m backend.stt download
"""
import io
import os
import sys
import time
import logging
import threading

logger = logging.getLogger(__name__)

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR   = os.getenv("WHISPER_MODELS_DIR", os.path.join(BASE_DIR, "models", "whisper"))
# tiny / base / small / medium / large-v3 / turbo… "small" = bon compromis français sur CPU
WHISPER_MODEL   = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE  = os.getenv("WHISPER_DEVICE", "auto")     # auto / cpu / cuda
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")    # int8 = rapide et léger sur CPU
WHISPER_LANG    = os.getenv("WHISPER_LANGUAGE", "fr")
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class STTUnavailable(Exception):
    pass


def decode_audio(audio: bytes, rate: int = 16000):
    """Décode n'importe quel format audio (webm/opus du navigateur, wav, mp3…) en mono float32.

    Implémenté ici plutôt que via faster_whisper.decode_audio, incompatible avec PyAV >= 15.
    """
    import av
    import numpy as np
    chunks = []
    with av.open(io.BytesIO(audio)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for frame in container.decode(audio=0):
            chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray() for f in resampler.resample(None))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


class WhisperSTT:
    def __init__(self, model: str = WHISPER_MODEL, models_dir: str = MODELS_DIR):
        self.model_name = model
        self.models_dir = models_dir
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def installed() -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.installed():
            raise STTUnavailable("faster-whisper n'est pas installé (pip install faster-whisper)")
        from faster_whisper import WhisperModel
        logger.info(f"🎤 Chargement du modèle Whisper '{self.model_name}' "
                    f"(téléchargé dans {self.models_dir} au premier lancement)…")
        t = time.time()
        try:
            self._model = WhisperModel(
                self.model_name, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE,
                download_root=self.models_dir,
            )
        except Exception as e:
            logger.exception("Erreur au chargement de Whisper")
            raise STTUnavailable(f"Impossible de charger Whisper '{self.model_name}' : {e}")
        logger.info(f"✅ Whisper prêt ({time.time() - t:.1f}s)")
        return self._model

    def status(self) -> dict:
        """État sans déclencher le chargement (qui peut télécharger plusieurs centaines de Mo)."""
        if not self.installed():
            return {"engine": "navigateur", "reason": "faster-whisper n'est pas installé"}
        return {"engine": "whisper", "model": self.model_name, "loaded": self._model is not None}

    def transcribe(self, audio: bytes, hint: str = "") -> dict:
        """Audio (webm, ogg, wav, mp3…) -> texte. Bloquant : à appeler dans un thread.

        `hint` : vocabulaire métier (noms de logiciels, tags…) qui aide Whisper à bien
        orthographier les termes techniques.
        """
        if len(audio) > MAX_AUDIO_BYTES:
            raise ValueError("Enregistrement trop long")
        try:
            samples = decode_audio(audio)
        except Exception as e:
            raise ValueError(f"Audio illisible : {e}")
        duration = len(samples) / 16000
        if duration < 0.3:
            return {"text": "", "duration": duration}

        t = time.time()
        with self._lock:
            model = self._load()
            segments, _info = model.transcribe(
                samples,
                language=WHISPER_LANG or None,
                beam_size=1,                 # réponse rapide : c'est une question courte
                vad_filter=True,             # ignore les silences / bruits de fond
                condition_on_previous_text=False,
                initial_prompt=hint or None,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
        logger.info(f"🎤 Transcription ({duration:.1f}s d'audio en {time.time() - t:.1f}s) : {text[:120]}")
        return {"text": text, "duration": duration}


stt = WhisperSTT()


if __name__ == "__main__":
    if sys.argv[1:] != ["download"]:
        sys.exit("Usage : python -m backend.stt download")
    from faster_whisper import download_model
    path = download_model(WHISPER_MODEL, cache_dir=MODELS_DIR)
    print(f"Modèle Whisper '{WHISPER_MODEL}' prêt : {path}")
