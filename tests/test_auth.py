from app.services.auth import hash_password, normalize_email, verify_password

def test_password_hash_roundtrip_and_wrong_password():
    encoded=hash_password('A-secure-password-123')
    assert verify_password('A-secure-password-123',encoded)
    assert not verify_password('wrong-password',encoded)
    assert 'A-secure-password-123' not in encoded

def test_email_normalization():
    assert normalize_email(' User@Example.COM ')=='user@example.com'
