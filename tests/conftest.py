import os
import sys
import importlib
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    """Module backend.main chargé avec un dossier de données temporaire."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.main as main
    return importlib.reload(main)


@pytest.fixture
def client(app_module):
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


@pytest.fixture
def fake_ollama(app_module, monkeypatch):
    """Remplace l'appel à Ollama par une réponse fixe (modifiable via .response)."""
    class Fake:
        response = "TITLE: Configuration VPN\nTAGS: VPN, FortiClient\n---\n# Configuration VPN\n\n## Résumé\nTest."
        calls = []

    async def ask(conversation, existing_tags=None, kind="story"):
        Fake.calls.append((conversation, existing_tags, kind))
        return Fake.response

    monkeypatch.setattr(app_module, "ask_ollama", ask)
    return Fake
