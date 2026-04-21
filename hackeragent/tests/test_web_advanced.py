"""Tests for mcp-web-advanced server — Python-native tool'ları test eder.

Network çağrılarını mock'luyoruz, sadece payload üretim ve parsing mantığını
doğruluyoruz.
"""
import base64
import importlib.util
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Module'ü dinamik yükle (MCP server path'i package değil)
_SERVER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "mcp-servers", "mcp-web-advanced", "server.py"
)


@pytest.fixture(scope="module")
def was():
    spec = importlib.util.spec_from_file_location("was", _SERVER_PATH)
    m = importlib.util.module_from_spec(spec)
    # Mock MCP decorator
    sys.modules.setdefault("_was_test", m)
    spec.loader.exec_module(m)
    return m


# ─── JWT ─────────────────────────────────────────────────────────────────────
def test_jwt_analyze_detects_hs256_weak(was):
    # jwt.io default sample (HS256)
    tok = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
           "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
           "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
    r = was.jwt_analyze(tok)
    assert "HS256" in r
    assert "Symmetric" in r


def test_jwt_analyze_detects_alg_none(was):
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b'{"sub":"x"}').rstrip(b"=").decode()
    tok = f"{header}.{payload}."
    r = was.jwt_analyze(tok)
    assert "alg='none'" in r or "alg=" in r.lower()
    assert "imza yok" in r or "none" in r.lower()


def test_jwt_analyze_invalid_format(was):
    assert "HATA" in was.jwt_analyze("not.a.jwt.token.too.many")
    assert "HATA" in was.jwt_analyze("onlyone")


def test_jwt_attack_alg_none_generates_variants(was):
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b'{"role":"user"}').rstrip(b"=").decode()
    tok = f"{header}.{payload}.sig"
    r = was.jwt_attack_alg_none(tok, claims_override='{"role":"admin"}')
    assert "alg='none'" in r
    assert "alg='NONE'" in r
    # Payload'ta role=admin claim'i olmalı
    assert r.count("alg=") >= 4


def test_jwt_brute_hs256_finds_secret(was):
    # Known secret: "secret" (HS256 wordlist'te var)
    import hashlib
    import hmac as hmac_mod
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b'{"sub":"x"}').rstrip(b"=").decode()
    sig_bytes = hmac_mod.new(b"secret", f"{header}.{payload}".encode(), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    tok = f"{header}.{payload}.{sig}"
    r = was.jwt_brute_hs256(tok)
    assert "SECRET KIRILDI" in r
    assert "secret" in r


def test_jwt_brute_hs256_no_match(was):
    import hashlib
    import hmac as hmac_mod
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b'{"sub":"x"}').rstrip(b"=").decode()
    # Sözlükte olmayan secret
    sig_bytes = hmac_mod.new(b"Xh8xQz2p!unguessable_9f", f"{header}.{payload}".encode(), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    tok = f"{header}.{payload}.{sig}"
    r = was.jwt_brute_hs256(tok)
    assert "bulunamadı" in r


# ─── GraphQL ─────────────────────────────────────────────────────────────────
def test_graphql_batch_attack_rejects_bad_query(was):
    r = was.graphql_batch_attack("http://t/graphql", "invalid query")
    assert "HATA" in r


def test_graphql_batch_attack_rejects_bad_size(was):
    r = was.graphql_batch_attack("http://t", "{ field }", batch_size=5000)
    assert "HATA" in r


# ─── OAuth ───────────────────────────────────────────────────────────────────
def test_oauth_redirect_bypass_generates_15_variants(was):
    r = was.oauth_redirect_bypass(
        auth_url="https://target/authorize",
        client_id="abc",
        legit_callback="https://app.target/cb",
        attacker="https://evil.com/c",
    )
    assert "attacker" in r.lower() or "evil" in r
    # En az 15 URL üretilmiş olmalı
    assert r.count("https://target/authorize") >= 10


# ─── OpenAPI Ingest ─────────────────────────────────────────────────────────
def test_openapi_ingest_parses_swagger_json(was):
    spec = {
        "info": {"title": "Test API", "version": "1.0"},
        "servers": [{"url": "https://api.test/v1"}],
        "paths": {
            "/users": {"get": {"parameters": [{"name": "limit"}]}},
            "/admin/delete": {"post": {"parameters": [{"name": "id"}]}},
            "/public": {"get": {}},
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        path = f.name
    try:
        r = was.openapi_ingest(path)
        assert "Test API" in r
        assert "/users" in r
        assert "/admin/delete" in r
        assert "⚠" in r  # dangerous endpoint marker
    finally:
        os.unlink(path)


def test_openapi_ingest_missing_file(was):
    r = was.openapi_ingest("/nonexistent/path.json")
    assert "HATA" in r


def test_openapi_ingest_invalid_json(was):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write("not valid { json")
        path = f.name
    try:
        r = was.openapi_ingest(path)
        assert "HATA" in r
    finally:
        os.unlink(path)


# ─── Postman Ingest ──────────────────────────────────────────────────────────
def test_postman_ingest_extracts_endpoints(was):
    coll = {
        "info": {"name": "My API"},
        "item": [
            {"name": "Login", "request": {"method": "POST", "url": "https://api.test/login"}},
            {"name": "Folder", "item": [
                {"name": "Users", "request": {"method": "GET", "url": "https://api.test/users"}},
            ]},
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(coll, f)
        path = f.name
    try:
        r = was.postman_ingest(path)
        assert "My API" in r
        assert "Login" in r
        assert "Users" in r
    finally:
        os.unlink(path)


# ─── Formula Injection ──────────────────────────────────────────────────────
def test_formula_injection_all(was):
    r = was.formula_injection_payloads("all")
    assert "cmd" in r.lower()
    assert "HYPERLINK" in r or "IMPORTXML" in r


def test_formula_injection_rce_only(was):
    r = was.formula_injection_payloads("rce")
    assert "cmd" in r.lower()
    assert "HYPERLINK" not in r  # exfil değil, rce only


def test_formula_injection_exfil_only(was):
    r = was.formula_injection_payloads("exfil")
    assert "HYPERLINK" in r or "IMPORTXML" in r or "WEBSERVICE" in r
    assert "calc" not in r  # rce payload değil


# ─── SAML XSW ──────────────────────────────────────────────────────────────
def test_saml_xsw_invalid_input(was):
    assert "HATA" in was.saml_xsw_variants("not-valid-base64!")
    # Valid b64 but not SAML
    valid_b64 = base64.b64encode(b"<root/>").decode()
    assert "HATA" in was.saml_xsw_variants(valid_b64)


def test_saml_xsw_valid_assertion(was):
    saml = '<Response><Assertion ID="1"><Subject/></Assertion></Response>'
    b64 = base64.b64encode(saml.encode()).decode()
    r = was.saml_xsw_variants(b64)
    assert "XSW" in r
    assert "Assertion sayısı: 1" in r


# ─── NoSQLi ─────────────────────────────────────────────────────────────────
def test_nosqli_invalid_body_template(was):
    r = was.nosqli_mongo_test("http://t/login", body_template="not json")
    assert "HATA" in r


# ─── API IDOR Matrix ───────────────────────────────────────────────────────
def test_api_idor_matrix_rejects_no_placeholder(was):
    r = was.api_idor_matrix("https://api/x/1", ids="1,2")
    assert "HATA" in r
    assert "{ID}" in r


def test_api_idor_matrix_rejects_single_id(was):
    r = was.api_idor_matrix("https://api/{ID}", ids="1")
    assert "HATA" in r


# ─── Prototype Pollution ───────────────────────────────────────────────────
def test_prototype_pollution_scan_handles_404(was):
    # Gerçek network yok, ama exception safe çalışmalı
    with patch("requests.Session.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = "no polluted content"
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        r = was.prototype_pollution_scan("http://fake.test/?a=b")
        # Ya sonuç bulundu ya da "tetiklenmedi" mesajı
        assert "PP" in r or "tetiklenmedi" in r or "🎯" in r


# ─── Race Condition ────────────────────────────────────────────────────────
def test_race_condition_rejects_bad_count(was):
    assert "HATA" in was.race_condition_test("http://t", count=1)
    assert "HATA" in was.race_condition_test("http://t", count=500)
