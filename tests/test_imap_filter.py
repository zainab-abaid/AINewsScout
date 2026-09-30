"""Which inbox headers count as a forwarded newsletter."""

from backend.services import imap_sync


def test_auto_forward_matches_on_the_original_recipient(monkeypatch):
    monkeypatch.setattr(imap_sync, "IMAP_ALLOWED_FROM", ["zainab.abaid@emumba.com"])
    assert imap_sync.headers_allowed(
        "AINews <swyx+ainews@substack.com>",
        "zainab.abaid@emumba.com",
        "zainab.abaid@emumba.com ainewsscout@gmail.com",
    )


def test_unrelated_mail_is_rejected(monkeypatch):
    monkeypatch.setattr(imap_sync, "IMAP_ALLOWED_FROM", ["zainab.abaid@emumba.com"])
    assert not imap_sync.headers_allowed(
        "Emumba Private Limited Team <forwarding-noreply@google.com>",
        "ainewsscout@gmail.com",
    )
