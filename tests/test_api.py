def test_generate_and_list(client, fake_ollama):
    r = client.post("/generate", json={"conversation": "User: VPN ?"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["title"] == "Configuration VPN"
    assert d["tags"] == ["forticlient", "vpn"]
    assert d["filename"] == "configuration_vpn.md"

    pages = client.get("/pages").json()
    assert [p["title"] for p in pages] == ["Configuration VPN"]
    assert client.get("/pages/configuration_vpn.md").json()["content"].startswith("# Configuration VPN")
    assert client.get("/tags").json() == [{"name": "forticlient", "count": 1}, {"name": "vpn", "count": 1}]


def test_existing_tags_are_passed_to_llm(client, fake_ollama):
    client.post("/generate", json={"conversation": "a"})
    client.post("/generate", json={"conversation": "b"})
    assert fake_ollama.calls[0][1] == []
    assert fake_ollama.calls[1][1] == ["forticlient", "vpn"]


def test_same_title_overwrites_different_title_same_slug_does_not(client, fake_ollama):
    client.post("/generate", json={"conversation": "a"})
    client.post("/generate", json={"conversation": "a"})
    assert len(client.get("/pages").json()) == 1

    fake_ollama.response = "TITLE: Configuration-VPN\nTAGS: vpn\n---\n# Autre"
    d = client.post("/generate", json={"conversation": "b"}).json()
    assert d["filename"] == "configuration_vpn_2.md"
    assert len(client.get("/pages").json()) == 2
    assert client.get("/pages/configuration_vpn.md").json()["content"].startswith("# Configuration VPN")


def test_empty_conversation(client, fake_ollama):
    assert client.post("/generate", json={"conversation": "   "}).status_code == 400
    assert fake_ollama.calls == []


def test_ollama_down_returns_503(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "OLLAMA_URL", "http://127.0.0.1:9")
    r = client.post("/generate", json={"conversation": "x"})
    assert r.status_code == 503
    assert "Cannot connect" in r.json()["error"]
    assert client.get("/health").json()["ollama"] == "ko"


def test_update_tags(client, fake_ollama):
    client.post("/generate", json={"conversation": "a"})
    r = client.put("/pages/configuration_vpn.md/tags", json={"tags": [" Réseau ", "vpn", "VPN"]})
    assert r.json()["tags"] == ["réseau", "vpn"]
    assert client.put("/pages/nope.md/tags", json={"tags": ["x"]}).status_code == 404


def test_delete_page(client, fake_ollama, app_module):
    import os
    client.post("/generate", json={"conversation": "a"})
    assert client.delete("/pages/configuration_vpn.md").status_code == 200
    assert client.get("/pages").json() == []
    assert not os.path.exists(os.path.join(app_module.WIKI_DIR, "configuration_vpn.md"))
    assert client.delete("/pages/configuration_vpn.md").status_code == 404


def test_path_traversal_is_rejected(client, app_module, tmp_path):
    (tmp_path / "secret.md").write_text("secret")
    assert client.get("/pages/..%2Fsecret.md").status_code == 404
    assert client.get("/pages/..%2Fwiki.db").status_code == 404
    assert client.delete("/pages/..%2Fsecret.md").status_code == 404
    assert (tmp_path / "secret.md").exists()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Local AI Ops Assistant" in r.text
