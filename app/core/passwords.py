"""Salted password storage using Python's PBKDF2 implementation."""
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000)
    return f'pbkdf2_sha256$600000${salt}${digest.hex()}'


def check_password(password: str, encoded: str | None) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (AttributeError, ValueError, TypeError):
        return False
