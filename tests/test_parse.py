from backend.main import parse_response


def test_standard_format():
    p = parse_response("TITLE: Config VPN\nTAGS: vpn, Forti Client\n---\n# Config VPN\n\n## Résumé\nOk")
    assert p["title"] == "Config VPN"
    assert p["tags"] == ["forti-client", "vpn"]
    assert p["content"].startswith("# Config VPN")
    assert "TITLE:" not in p["content"]


def test_think_block_is_stripped():
    raw = "<think>\nJe réfléchis...\n---\nTITLE: piège\n</think>\nTITLE: Vrai titre\nTAGS: docker\n---\n# Vrai titre"
    p = parse_response(raw)
    assert p["title"] == "Vrai titre"
    assert p["tags"] == ["docker"]
    assert "réfléchis" not in p["content"]


def test_markdown_decorated_headers():
    p = parse_response("**TITLE:** Nginx reverse proxy\n**Tags:** nginx, ssl\n\n---\n# Nginx\ntexte")
    assert p["title"] == "Nginx reverse proxy"
    assert p["tags"] == ["nginx", "ssl"]
    assert p["content"] == "# Nginx\ntexte"


def test_horizontal_rule_in_body_is_kept():
    p = parse_response("TITLE: A\nTAGS: x\n---\n# A\n\nhaut\n\n---\n\nbas")
    assert "haut" in p["content"] and "bas" in p["content"]


def test_fallback_on_heading_and_fenced_block():
    p = parse_response("```markdown\n# Sauvegarde Postgres\n\n## Résumé\npg_dump\n```")
    assert p["title"] == "Sauvegarde Postgres"
    assert p["tags"] == []
    assert p["content"].startswith("# Sauvegarde Postgres")


def test_no_title_at_all():
    p = parse_response("juste du texte")
    assert p["title"] == "Sans titre"
    assert p["content"] == "juste du texte"
