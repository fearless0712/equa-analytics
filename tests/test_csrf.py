from app.security.csrf import CsrfProtector


def test_csrf_token_is_signed_and_expires() -> None:
    protector = CsrfProtector("test-secret", ttl_seconds=60)
    token = protector.issue(now=1_000)
    assert protector.validate(token, now=1_060)
    assert not protector.validate(token, now=1_061)
    assert not protector.validate(token + "tampered", now=1_010)
    assert not protector.validate("malformed", now=1_010)
