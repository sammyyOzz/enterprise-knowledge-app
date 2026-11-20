"""Password hashing with Argon2id (argon2-cffi defaults follow current OWASP guidance)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Verified when the email doesn't exist, so "no such user" takes as long as "wrong password"
# and response timing doesn't reveal which emails have accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):  # mismatch, or a placeholder/garbage hash
        return False


def verify_dummy(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def needs_rehash(stored_hash: str) -> bool:
    """True if the hash was made with weaker parameters than today's defaults."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False