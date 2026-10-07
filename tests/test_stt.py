import io
import math
import wave

import pytest

from backend.stt import WhisperSTT

pytest.importorskip("faster_whisper")


def wav_bytes(seconds=1.0, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = bytearray()
        for i in range(int(seconds * rate)):
            v = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
            frames += v.to_bytes(2, "little", signed=True)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def webm_opus_bytes(seconds=1.0):
    """Même format que le MediaRecorder de Chrome / Firefox."""
    import av
    import numpy as np
    buf = io.BytesIO()
    with av.open(buf, "w", format="webm") as out:
        stream = out.add_stream("libopus", rate=48000)
        t = np.arange(int(seconds * 48000)) / 48000
        samples = (np.sin(2 * np.pi * 440 * t) * 8000).astype("int16").reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()


class FakeSegment:
    def __init__(self, text): self.text = text


class FakeWhisper:
    def __init__(self):
        self.calls = []

    def transcribe(self, samples, **kw):
        self.calls.append({"seconds": len(samples) / 16000, **kw})
        return iter([FakeSegment(" Le VPN reste bloqué"), FakeSegment(" à 98 %. ")]), None


@pytest.fixture
def fake_stt(app_module, monkeypatch):
    engine = WhisperSTT()
    engine._model = FakeWhisper()
    monkeypatch.setattr(app_module, "stt", engine)
    return engine._model


@pytest.mark.parametrize("make_audio", [wav_bytes, webm_opus_bytes])
def test_transcribe_real_audio_formats(client, fake_stt, make_audio):
    r = client.post("/stt", content=make_audio(1.0), headers={"Content-Type": "audio/webm"})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "Le VPN reste bloqué à 98 %."
    call = fake_stt.calls[0]
    assert 0.9 < call["seconds"] < 1.2
    assert call["language"] == "fr" and call["vad_filter"] is True


def test_vocabulary_from_knowledge_base_is_passed(client, fake_ollama, fake_stt):
    fake_ollama.response = "TITLE: VPN FortiClient bloqué\nTAGS: forticlient, vpn\n---\n# x"
    client.post("/generate", json={"conversation": "x"})
    client.post("/stt", content=wav_bytes())
    assert "forticlient" in fake_stt.calls[0]["initial_prompt"]
    assert "VPN FortiClient bloqué" in fake_stt.calls[0]["initial_prompt"]


def test_too_short_or_invalid_audio(client, fake_stt):
    assert client.post("/stt", content=wav_bytes(0.1)).json()["text"] == ""
    assert fake_stt.calls == []
    assert client.post("/stt", content=b"pas de l'audio").status_code == 400
    assert client.post("/stt", content=b"").status_code == 400


def test_health_reports_whisper(client, fake_stt):
    stt_status = client.get("/health").json()["stt"]
    assert stt_status["engine"] == "whisper" and stt_status["loaded"] is True


def test_whisper_not_installed(client, app_module, monkeypatch):
    engine = WhisperSTT()
    monkeypatch.setattr(WhisperSTT, "installed", staticmethod(lambda: False))
    monkeypatch.setattr(app_module, "stt", engine)
    assert client.get("/health").json()["stt"]["engine"] == "navigateur"
    assert client.post("/stt", content=wav_bytes()).status_code == 503
