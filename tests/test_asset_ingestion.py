import socket

import pytest

from app.services.assets import validate_public_image_url


def test_image_url_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="HTTP"):
        validate_public_image_url("file:///etc/passwd")


def test_image_url_rejects_private_address(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="本机或内网"):
        validate_public_image_url("https://example.test/image.jpg")


def test_image_url_accepts_public_address(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    assert validate_public_image_url("https://example.com/image.jpg") == "https://example.com/image.jpg"

