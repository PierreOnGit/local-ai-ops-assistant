"""Synthèse vocale locale avec Piper (https://github.com/OHF-Voice/piper1-gpl).

Optionnel : si piper-tts n'est pas installé ou si la voix est absente, l'API
renvoie 503 et le frontend se rabat sur la synthèse vocale du navigateur.

Télécharger la voix par défaut :
    python -m piper.download_voices fr_FR-siwis-medium --download-dir voices
"""
import io
import os
import wave
import logging
import threading

logger = logging.getLogger(__name__)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICES_DIR  = os.getenv("PIPER_VOICES_DIR", os.path.join(BASE_DIR, "voices"))
PIPER_VOICE = os.getenv("PIPER_VOICE", "fr_FR-siwis-medium")
MAX_CHARS   = 1000


class TTSUnavailable(Exception):
    pass


class PiperTTS:
    def __init__(self, voice: str = PIPER_VOICE, voices_dir: str = VOICES_DIR):
        self.voice_name = voice
        self.voices_dir = voices_dir
        self._voice = None
        self._error = None
        self._lock = threading.Lock()

    @property
    def model_path(self) -> str:
        # PIPER_VOICE peut être un chemin vers un .onnx ou un nom de voix
        if self.voice_name.endswith(".onnx"):
            return self.voice_name
        return os.path.join(self.voices_dir, f"{self.voice_name}.onnx")

    def _load(self):
        if self._voice is not None:
            return self._voice
        if self._error:
            raise TTSUnavailable(self._error)
        try:
            from piper import PiperVoice
        except ImportError:
            self._error = "piper-tts n'est pas installé (pip install piper-tts)"
            raise TTSUnavailable(self._error)
        if not os.path.exists(self.model_path):
            # Pas mémorisé : la voix peut être téléchargée sans redémarrer l'app
            raise TTSUnavailable(
                f"Voix Piper introuvable ({self.model_path}). "
                f"Lance : python -m piper.download_voices {self.voice_name} --download-dir {self.voices_dir}"
            )
        logger.info(f"🔊 Chargement de la voix Piper : {self.model_path}")
        self._voice = PiperVoice.load(self.model_path)
        return self._voice

    def status(self) -> dict:
        try:
            with self._lock:
                self._load()
            return {"engine": "piper", "voice": self.voice_name}
        except TTSUnavailable as e:
            return {"engine": "navigateur", "reason": str(e)}
        except Exception as e:
            logger.exception("Erreur au chargement de Piper")
            return {"engine": "navigateur", "reason": f"Erreur Piper : {e}"}

    def synthesize(self, text: str) -> bytes:
        """Texte -> fichier WAV (bytes). Bloquant : à appeler dans un thread."""
        text = " ".join(text.split())[:MAX_CHARS]
        buf = io.BytesIO()
        with self._lock:
            voice = self._load()
            with wave.open(buf, "wb") as wav:
                voice.synthesize_wav(text, wav)
        return buf.getvalue()


tts = PiperTTS()
