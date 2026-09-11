import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_and_verified() -> None:
    encoded = hash_password("correct horse battery staple")

    assert "correct horse" not in encoded
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_access_token_is_signed() -> None:
    token = create_access_token("9ad1ff8a-90c0-4ec8-9c5d-1ea2737571c6", {"role": "ADMIN"})

    assert decode_access_token(token)["role"] == "ADMIN"
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{token}tampered")
