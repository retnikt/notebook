import re
from time import time

import jwt
from pytest import approx
from starlette.testclient import TestClient

from notebook import app
from notebook.routes.oauth2 import ALGORITHM, AUDIENCE, EXPIRY, ISSUER
from notebook.settings import settings

ASCII = set(range(0x20, 0x7F))

# generated by https://abnf.msweet.org/ from RFC 3986
with open("tests/data/uri.regex.txt") as f:
    URI = re.compile(f.readline().rstrip())


settings.rocpf_origins = ["origin.example.com"]

client = TestClient(app)
now2 = time()
valid_token = jwt.encode(
    {
        "sub": "admin@example.com",
        "iat": now2,
        "nbf": now2,
        "exp": now2 + 3600,
        "aud": AUDIENCE,
        "iss": ISSUER,
        "scope": ["some", "test", "scopes"],
    },
    key=settings.secret_key,
    algorithm=ALGORITHM,
).decode()


def _test_success_response(response):
    now = time()

    assert response.status_code == 200
    json = response.json()
    assert json["token_type"].lower() == "bearer"
    assert isinstance(scope := json.get("scope", ""), str)
    assert isinstance(expiry := json["expires_in"], int)

    token = json["access_token"]
    decoded = jwt.decode(
        token, key=settings.secret_key, audience=AUDIENCE, issuer=ISSUER
    )
    assert decoded["sub"] == "admin@example.com"
    assert decoded["scope"] == scope.split(" ")
    assert approx(now, decoded["iat"], abs=1)
    assert approx(now, decoded["nbf"], abs=1)
    assert approx(now, decoded["exp"] + expiry, abs=1)
    assert isinstance(decoded["iss"], str)
    assert isinstance(decoded["aud"], str)

    assert response.headers["pragma"] == "no-cache"
    assert response.headers["cache-control"] == "no-store"


def _test_error_response(json, headers):
    # see RFC 6749.5.2

    error_description = json.get("error_description", "")
    assert isinstance(error_description, str)
    assert set(error_description.encode()) <= (ASCII - {"\\", '"'})
    error_uri = json.get("error_uri")
    if error_uri:
        assert isinstance(error_uri, str)
        assert set(error_description.encode()) <= (ASCII - {" ", "\\", '"'})
        assert URI.match(error_uri)

    assert headers["pragma"] == "no-cache"
    assert headers["cache-control"] == "no-store"


def test_ropcf_success():
    response = client.post(
        "/api/oauth2/ropcf",
        {
            "username": "admin@example.com",
            "password": "hunter2",
            "grant_type": "password",
        },
        headers={"Origin": "origin.example.com"},
    )
    _test_success_response(response)


def test_ropcf_incorrect_password():
    response = client.post(
        "/api/oauth2/ropcf",
        {
            "username": "admin@example.com",
            "password": "incorrect",
            "grant_type": "password",
        },
        headers={"Origin": "origin.example.com"},
    )
    assert response.status_code >= 400
    json = response.json()
    assert json["error"] == "invalid_grant"
    _test_error_response(json, response.headers)


def test_ropcf_incorrect_email():
    response = client.post(
        "/api/oauth2/ropcf",
        {
            "username": "admin@example.invalid",
            "password": "password",
            "grant_type": "password",
        },
        headers={"Origin": "origin.example.com"},
    )
    assert response.status_code >= 400
    json = response.json()
    assert json["error"] == "invalid_grant"
    _test_error_response(json, response.headers)


def test_ropcf_invalid_grant_type():
    response = client.post(
        "/api/oauth2/ropcf",
        {
            "username": "admin@example.com",
            "password": "password",
            "grant_type": "invalid",
        },
        headers={"Origin": "origin.example.com"},
    )
    assert response.status_code >= 400
    json = response.json()
    assert json["error"] == "unsupported_grant"
    _test_error_response(json, response.headers)


def test_ropcf_missing_field():
    data_original = {
        "username": "admin@example.com",
        "password": "password",
        "grant_type": "password",
    }
    for missing in "username", "password", "grant_type":
        data = data_original.copy()
        del data[missing]
        response = client.post(
            "/api/oauth2/ropcf", data, headers={"Origin": "origin.example.com"}
        )
        assert response.status_code >= 400
        json = response.json()
        assert json["error"] == "invalid_request"
        _test_error_response(json, response.headers)


def test_ropcf_wrong_content_type():
    response = client.post(
        "/api/oauth2/ropcf",
        "custom_data_here",
        headers={"Origin": "origin.example.com"},
    )
    assert response.status_code >= 400
    json = response.json()
    assert json["error"] == "invalid_request"
    _test_error_response(json, response.headers)


def test_ropcf_wrong_origin():
    response = client.post(
        "/api/oauth2/ropcf",
        {
            "username": "admin@example.com",
            "password": "hunter2",
            "grant_type": "password",
        },
        headers={"Origin": "origin.example.invalid"},
    )
    assert response.status_code >= 400
    json = response.json()
    assert json["error"] == "invalid_client"
    _test_error_response(json, response.headers)


def test_refresh_token():
    response = client.post(
        "/api/oauth2/refresh", headers={"Authorization": "Bearer " + valid_token}
    )

    _test_success_response(response)


def test_refresh_expired_token():
    now = time()
    token = jwt.encode(
        {
            "sub": "admin@example.com",
            "iat": now - EXPIRY - 3600,
            "nbf": now - EXPIRY - 3600,
            "exp": now - 3600,
            "aud": AUDIENCE,
            "iss": ISSUER,
            "scope": "some test scopes",
        },
        key=settings.secret_key,
        algorithm=ALGORITHM,
    ).decode()

    response = client.post(
        "/api/oauth2/refresh", headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code >= 400
    assert response.json()


def test_refresh_invalid_token():
    token = "totally.invalid.token"

    response = client.post(
        "/api/oauth2/refresh", headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code >= 400
    assert response.json()


def test_refresh_not_invalid_auth():
    for authorization in (
        "",
        "Bearer",
        "Bearer ",
        f"Invalid {valid_token}",
        "Bearer {valid_token} ",
        "Bearer {valid_token} invalid",
        "bEaRer {valid_token}",
    ):
        response = client.post(
            "/api/oauth2/refresh", headers={"Authorization": authorization}
        )
        assert response.status_code >= 400
        assert response.json()
