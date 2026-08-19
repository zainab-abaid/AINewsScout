from __future__ import annotations

from backend.services.links import hydrate_excerpt_links, normalize_inline_links
from backend.services.mailparse import gmail_payload_text, html_to_markdown


SAMPLE = (
    "Agent skills are being demystified and operationalized: @omarsar0’s summary of "
    "“Demystifying Agent Skills” [ https://substack.com/redirect/e04be533-c1f9-456c-94f2-8567425c4e0a?j=eyJ1IjoiM2YzenRqIn0.abc ] "
    "is useful because it quantifies a common intuition: skills help mostly through "
    "procedural anchoring (65.7%), not factual knowledge injection (4.5%). Precision "
    "also collapses as skill pools expand. Related posts on the “skills” paper "
    "[ https://substack.com/redirect/e982bb62-5be3-4228-8596-ea401bb46af1?j=eyJ1IjoiM2YzenRqIn0.abc ] "
    "and GitSkills dataset mining ~3.8M SKILL.md files "
    "[ https://substack.com/redirect/4bd73a14-9624-45e8-9b5b-1ad4775b5f13?j=eyJ1IjoiM2YzenRqIn0.abc ] "
    "point to a maturing ecosystem around discoverability, packaging, and trigger "
    "management for agent skill libraries."
)

EXCERPT_NO_LINKS = (
    "Agent skills are being demystified and operationalized: @omarsar0’s summary of "
    "“Demystifying Agent Skills” is useful because it quantifies a common intuition: "
    "skills help mostly through procedural anchoring (65.7%), not factual knowledge "
    "injection (4.5%). Precision also collapses as skill pools expand. Related posts "
    "on the “skills” paper and GitSkills dataset mining ~3.8M SKILL.md files point to "
    "a maturing ecosystem around discoverability, packaging, and trigger management "
    "for agent skill libraries."
)


def test_normalize_quoted_bracket_urls():
    out = normalize_inline_links(SAMPLE)
    assert "[“Demystifying Agent Skills”](https://substack.com/redirect/e04be533" in out
    assert "[“skills” paper](https://substack.com/redirect/e982bb62" in out
    assert "substack.com](https://substack.com/redirect/4bd73a14" in out
    assert "[ https://" not in out


def test_hydrate_restores_dropped_urls():
    out = hydrate_excerpt_links(EXCERPT_NO_LINKS, SAMPLE)
    assert "https://substack.com/redirect/e04be533" in out
    assert "https://substack.com/redirect/e982bb62" in out
    assert "https://substack.com/redirect/4bd73a14" in out
    assert "[“Demystifying Agent Skills”]" in out


def test_hydrate_from_markdown_links():
    body = normalize_inline_links(SAMPLE)
    out = hydrate_excerpt_links(EXCERPT_NO_LINKS, body)
    assert "https://substack.com/redirect/e04be533" in out
    assert "[“Demystifying Agent Skills”]" in out


def test_html_anchor_becomes_markdown_link():
    html = (
        '<p>See <a href="https://example.com/paper">Demystifying Agent Skills</a> '
        "for details.</p>"
    )
    md = html_to_markdown(html)
    assert md == "See [Demystifying Agent Skills](https://example.com/paper) for details."


def test_gmail_prefers_html_links_over_stripped_plain():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": ""},
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": __import__("base64").urlsafe_b64encode(
                        b'<p>Read <a href="https://example.com/x">the paper</a> today.</p>'
                    ).decode("ascii")
                },
            },
        ],
    }
    text = gmail_payload_text(payload)
    assert "[the paper](https://example.com/x)" in text
