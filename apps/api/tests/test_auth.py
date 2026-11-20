import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.auth.csrf import make_origin_guard
from api.auth.passwords import hash_password, needs_rehash, verify_dummy, verify_password
from api.auth.ratelimit import RateLimiter
from api.auth.roles import role_allows
from api.auth.tokens import hash_token, new_token
from api.enums.enums import WorkspaceRole
from api.schemas.auth import LoginRequest, SignupRequest


# ----------------------------- passwords ----------------------------- #
def test_hash_and_verify_roundtrip():
    stored = hash_password("correct horse battery")
    assert stored != "correct horse battery" and stored.startswith("$argon2id$")
    assert verify_password(stored, "correct horse battery")
    assert not verify_password(stored, "wrong password")


def test_hashes_are_salted():
    assert hash_password("same password!!") != hash_password("same password!!")


def test_placeholder_and_garbage_hashes_never_verify():
    assert not verify_password("!seed-placeholder", "anything")
    assert not verify_password("", "anything")
    assert needs_rehash("!seed-placeholder") is False  # must not raise


def test_dummy_verification_does_not_raise():
    verify_dummy("whatever")


# ------------------------------- tokens ------------------------------- #
def test_tokens_are_random_and_hashes_are_stable():
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40
    assert hash_token(a) == hash_token(a) and len(hash_token(a)) == 64
    assert hash_token(a) != hash_token(b) and hash_token(a) != a


# -------------------------------- roles -------------------------------- #
@pytest.mark.parametrize(
    "actual,minimum,allowed",
    [
        (WorkspaceRole.OWNER, WorkspaceRole.EDITOR, True),
        (WorkspaceRole.EDITOR, WorkspaceRole.EDITOR, True),
        (WorkspaceRole.EDITOR, WorkspaceRole.OWNER, False),
        (WorkspaceRole.VIEWER, WorkspaceRole.EDITOR, False),
        (WorkspaceRole.VIEWER, WorkspaceRole.VIEWER, True),
        (WorkspaceRole.OWNER, WorkspaceRole.VIEWER, True),
    ],
)
def test_role_hierarchy(actual, minimum, allowed):
    assert role_allows(actual, minimum) is allowed


# ----------------------------- rate limiter ----------------------------- #
class FakeRedis:
    def __init__(self):
        self.counts, self.ttls, self.expired_calls = {}, {}, []

    def pipeline(self):
        outer = self

        class Pipe:
            def __init__(self):
                self.ops = []

            def incr(self, key):
                self.ops.append(("incr", key))

            def ttl(self, key):
                self.ops.append(("ttl", key))

            def execute(self):
                out = []
                for op, key in self.ops:
                    if op == "incr":
                        outer.counts[key] = outer.counts.get(key, 0) + 1
                        out.append(outer.counts[key])
                    else:
                        out.append(outer.ttls.get(key, -1))
                return out

        return Pipe()

    def expire(self, key, seconds):
        self.ttls[key] = seconds
        self.expired_calls.append(key)

    def delete(self, key):
        self.counts.pop(key, None)
        self.ttls.pop(key, None)


def test_rate_limit_blocks_after_limit_and_reports_retry_after():
    limiter = RateLimiter(FakeRedis())
    results = [limiter.hit("login:ip:a@b.c", limit=3, window_seconds=900) for _ in range(5)]
    assert [allowed for allowed, _ in results] == [True, True, True, False, False]
    assert all(0 < retry <= 900 for _, retry in results)


def test_rate_limit_sets_expiry_once_and_reset_clears():
    redis = FakeRedis()
    limiter = RateLimiter(redis)
    for _ in range(3):
        limiter.hit("k", limit=10, window_seconds=60)
    assert redis.expired_calls == ["k"]  # only the first hit starts the window
    limiter.reset("k")
    assert limiter.hit("k", limit=1, window_seconds=60)[0] is True


def test_rate_limit_fails_open_when_redis_is_down():
    class Broken:
        def pipeline(self):
            raise ConnectionError("redis down")

        def delete(self, key):
            raise ConnectionError("redis down")

    limiter = RateLimiter(Broken())
    assert limiter.hit("k", limit=1, window_seconds=60) == (True, 0)
    limiter.reset("k")  # must not raise


# ------------------------------ origin guard ------------------------------ #
def make_client():
    app = FastAPI()
    app.middleware("http")(make_origin_guard({"http://localhost:3000"}))

    @app.post("/thing")
    def post_thing():
        return {"ok": True}

    @app.get("/thing")
    def get_thing():
        return {"ok": True}

    return TestClient(app)


def test_origin_guard_allows_trusted_origin_and_missing_origin():
    client = make_client()
    assert client.post("/thing", headers={"Origin": "http://localhost:3000"}).status_code == 200
    assert client.post("/thing").status_code == 200  # curl / scripts


def test_origin_guard_blocks_foreign_origin_on_unsafe_methods_only():
    client = make_client()
    assert client.post("/thing", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/thing", headers={"Origin": "null"}).status_code == 403
    assert client.get("/thing", headers={"Origin": "https://evil.example"}).status_code == 200


# ------------------------------- schemas ------------------------------- #
def test_signup_normalises_email_and_enforces_password_length():
    ok = SignupRequest(email="  Sam@Example.COM ", password="long enough pw", organization_name="Acme")
    assert ok.email == "sam@example.com"
    with pytest.raises(ValidationError):
        SignupRequest(email="sam@example.com", password="short", organization_name="Acme")
    with pytest.raises(ValidationError):
        SignupRequest(email="not-an-email", password="long enough pw", organization_name="Acme")


def test_login_normalises_email():
    assert LoginRequest(email="A@B.co", password="x").email == "a@b.co"