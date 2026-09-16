from __future__ import annotations

import pytest

from coador.redact import REDACTED, sanitize_snippet

LEAKS = [
    'apiKey = "super-secret-value"',
    'val CLIENT_SECRET: String = "abc123def456"',
    'buildConfigField("String", "API_KEY", "\\"live-key\\"")',
    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
    'consentAppId = "11111111-2222-4333-8444-555555555555"',
    'contentProjectId = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"',
    'signingHash = "a3f1b2c4d5e6f708192a3b4c5d6e7f8091a2b3c4"',
    'token: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"',
]


@pytest.mark.parametrize("snippet", LEAKS)
def test_secrets_are_redacted(snippet: str) -> None:
    assert REDACTED in sanitize_snippet(snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        'implementation("com.squareup.retrofit2:retrofit:2.11.0")',
        'testInstrumentationRunner = "com.example.HiltTestRunner"',
        'applicationId = "com.example.mini"',
        "minSdk = 26",
        'versionName = "1.0.3"',
    ],
)
def test_ordinary_configuration_is_left_alone(snippet: str) -> None:
    assert sanitize_snippet(snippet) == snippet


def test_uuid_values_are_redacted_anywhere_in_the_line() -> None:
    line = "consentId=11111111-2222-4333-8444-555555555555 # production"
    sanitized = sanitize_snippet(line)
    assert "11111111" not in sanitized
    assert sanitized.endswith("# production")


def test_empty_input_is_returned_unchanged() -> None:
    assert sanitize_snippet("") == ""


def test_numeric_password_is_not_confused_with_a_configuration_count() -> None:
    assert sanitize_snippet("password=123456") == f"password={REDACTED}"
    assert sanitize_snippet("token_count = 42") == "token_count = 42"


@pytest.mark.parametrize(
    "value",
    [
        'accessToken = "CANARY_LEFT" + "CANARY_RIGHT"',
        'accessToken = "CANARY_LEFT" +\n "CANARY_RIGHT"',
        'accessToken = "CANARY_LEFT" + suffix + "CANARY_RIGHT"',
        'accessToken = """CANARY_LEFT""" + "CANARY_RIGHT"',
        'accessToken = "CANARY_LEFT" + suffix() + "CANARY_RIGHT"',
        'accessToken = prefix() + "CANARY_RIGHT"',
        'accessToken = "CANARY_LEFT" + suffix("CANARY_ARGUMENT") + "CANARY_RIGHT"',
        'accessToken = "CANARY_LEFT" + suffix[0] + "CANARY_RIGHT"',
        'accessToken = prefix()+"CANARY_RIGHT"',
        'refreshToken = primary ?: "CANARY_FALLBACK"',
        'refreshToken = primary\n ?: "CANARY_FALLBACK"',
        'refreshToken = primary ?: \n "CANARY_FALLBACK"',
        'refreshToken = if (enabled) "CANARY_LEFT" else "CANARY_RIGHT"',
    ],
)
def test_concatenated_secret_values_are_redacted_completely(value: str) -> None:
    safe = sanitize_snippet(value)
    assert "CANARY" not in safe
    assert sanitize_snippet(safe) == safe
    assert safe.count("\n") == value.count("\n")


@pytest.mark.parametrize(
    "text",
    [
        "password=CANARY_UNQUOTED",
        '"api_key": "CANARY_JSON"',
        'val TOKEN = "CANARY_ESCAPED\\"CANARY_TAIL"',
        'secret = """CANARY_FIRST\nCANARY_SECOND"""',
        "token: |\n  CANARY_FIRST\n  CANARY_SECOND\nnext: ok\n",
        '<string name="api_key">CANARY_XML</string>',
        "https://user:CANARY_PASSWORD@example.test/path?token=CANARY_QUERY&ok=yes",
        "Authorization: Bearer CANARY_HEADER",
        "X-API-Key: CANARY_HEADER",
        "Cookie: session=CANARY_COOKIE",
        "-----BEGIN PRIVATE KEY-----\nCANARY_KEY\n-----END PRIVATE KEY-----",
        *LEAKS,
    ],
)
def test_policy_is_idempotent_and_covers_contextual_values(text: str) -> None:
    safe = sanitize_snippet(text)
    assert "CANARY" not in safe
    assert sanitize_snippet(safe) == safe
    assert safe.count("\n") == text.count("\n")


@pytest.mark.parametrize(
    "text",
    [
        "token_count = 42",
        "secretsEnabled = true",
        "https://example.test/help?q=android",
        "class TokenProvider",
        "val tokenProvider = getProvider()",
        "minSdk = 26",
    ],
)
def test_useful_identifiers_and_nonsecret_values_survive(text: str) -> None:
    assert sanitize_snippet(text) == text
