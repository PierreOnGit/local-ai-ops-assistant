import json
import pytest

from backend.chat import ThinkFilter, ToolsUnsupported


PAGES = {
    "vpn": "TITLE: Configuration VPN FortiClient\nTAGS: vpn, réseau\n---\n# VPN\nGateway vpn.entreprise.fr, login AD.",
    "imprimante": "TITLE: Imprimante bloquée\nTAGS: impression\n---\n# Imprimante\nRedémarrer le spooler : net stop spooler.",
}


@pytest.fixture
def kb(client, fake_ollama):
    for raw in PAGES.values():
        fake_ollama.response = raw
        assert client.post("/generate", json={"conversation": "x"}).status_code == 200
    return client


class FakeLLM:
    """Faux /api/chat : chaque appel consomme le tour suivant du scénario."""
    def __init__(self, rounds, tools_supported=True):
        self.rounds, self.calls, self.tools_supported = list(rounds), [], tools_supported

    async def __call__(self, messages, tools=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if tools and not self.tools_supported:
            raise ToolsUnsupported()
        for chunk in self.rounds.pop(0):
            yield chunk


def text(*parts):
    return [{"message": {"content": p}} for p in parts]


def tool_call(name, **args):
    return [{"message": {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}}]


def chat(client, question, voice=True):
    r = client.post("/chat", json={"messages": [{"role": "user", "content": question}], "voice": voice})
    assert r.status_code == 200
    return [json.loads(l) for l in r.text.splitlines() if l]


# ── Recherche ──

def test_search_ignores_accents_and_stopwords(kb):
    res = kb.get("/search", params={"q": "comment je configure le reseau ?"}).json()
    assert [r["title"] for r in res] == ["Configuration VPN FortiClient"]
    assert kb.get("/search", params={"q": "spooler"}).json()[0]["title"] == "Imprimante bloquée"
    assert kb.get("/search", params={"q": "le la de ?"}).json() == []


def test_index_follows_tags_and_delete(kb):
    kb.put("/pages/imprimante_bloquée.md/tags", json={"tags": ["hp"]})
    assert kb.get("/search", params={"q": "hp"}).json()[0]["filename"] == "imprimante_bloquée.md"
    kb.delete("/pages/imprimante_bloquée.md")
    assert kb.get("/search", params={"q": "spooler"}).json() == []


def test_index_rebuilt_at_startup(kb, app_module):
    import importlib
    with app_module.db() as con:
        con.execute("DELETE FROM pages_fts")
        con.commit()
    importlib.reload(app_module)
    assert app_module.search_pages("forticlient")[0]["title"] == "Configuration VPN FortiClient"


# ── Agent ──

def test_fast_path_answers_from_injected_pages(kb, app_module, monkeypatch):
    llm = FakeLLM([text("<thi", "nk>hmm</think>", "D'abord ouvre ", "FortiClient.")])
    monkeypatch.setattr(app_module, "ollama_chat_stream", llm)
    events = chat(kb, "Comment configurer le VPN ?")

    assert events[0]["type"] == "search" and events[0]["mode"] == "rapide"
    assert events[0]["results"][0]["title"] == "Configuration VPN FortiClient"
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert answer == "D'abord ouvre FortiClient."
    assert events[-1]["type"] == "done"
    assert events[-1]["sources"][0]["filename"] == "configuration_vpn_forticlient.md"
    system = llm.calls[0]["messages"][0]["content"]
    assert "vpn.entreprise.fr" in system and "VOIX HAUTE" in system
    assert llm.calls[0]["tools"]


def test_deep_search_with_tools(kb, app_module, monkeypatch):
    llm = FakeLLM([
        text("Je cherche…") + tool_call("search_docs", query="spooler"),
        tool_call("read_doc", filename="imprimante_bloquée.md"),
        text("Redémarre le spooler."),
    ])
    monkeypatch.setattr(app_module, "ollama_chat_stream", llm)
    events = chat(kb, "L'impression ne marche plus du tout", voice=False)
    types = [e["type"] for e in events]

    assert types.count("search") == 2
    assert [e for e in events if e["type"] == "search"][1]["mode"] == "approfondi"
    assert "reset" in types and "read" in types
    assert events[-1]["answer"] == "Redémarre le spooler."
    assert "imprimante_bloquée.md" in [s["filename"] for s in events[-1]["sources"]]
    tool_msgs = [m for m in llm.calls[2]["messages"] if m["role"] == "tool"]
    assert "spooler" in tool_msgs[0]["content"] and "net stop spooler" in tool_msgs[1]["content"]


def test_tool_rounds_are_capped(kb, app_module, monkeypatch):
    llm = FakeLLM([tool_call("search_docs", query="x")] * 4 + [text("Rien trouvé.")])
    monkeypatch.setattr(app_module, "ollama_chat_stream", llm)
    events = chat(kb, "question introuvable")
    assert events[-1]["answer"] == "Rien trouvé."
    assert llm.calls[-1]["tools"] is None


def test_model_without_tools_falls_back(kb, app_module, monkeypatch):
    llm = FakeLLM([text("Réponse simple.")], tools_supported=False)
    monkeypatch.setattr(app_module, "ollama_chat_stream", llm)
    events = chat(kb, "vpn")
    assert any(e["type"] == "info" for e in events)
    assert events[-1]["answer"] == "Réponse simple."
    assert "search_docs" not in llm.calls[-1]["messages"][0]["content"]


def test_ollama_down_emits_error(kb, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "OLLAMA_URL", "http://127.0.0.1:9")
    events = chat(kb, "vpn")
    assert events[-1]["type"] == "error" and "Cannot connect" in events[-1]["error"]


def test_think_filter_split_tags():
    f = ThinkFilter()
    out = "".join(f.feed(c) for c in ["a<", "think>x</th", "ink> b <", "b>"]) + f.flush()
    assert out == "a b <b>"
