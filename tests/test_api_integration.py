"""Calling the API from another app: file sessions, response formats, async jobs and the error envelope."""

import base64
import io
import json
import time

import pytest
from openpyxl import load_workbook

from config import get_settings

XLSX_MAGIC = b"PK"


class FakeRedis:
    """Just enough of redis.asyncio.Redis for file sessions and download links."""
    store: dict = {}

    async def set(self, key, value, ex=None):
        self.store[key] = (value if isinstance(value, bytes) else str(value).encode(), time.time() + (ex or 3600))

    async def get(self, key):
        item = self.store.get(key)
        return item[0] if item and item[1] > time.time() else None

    async def expire(self, key, ttl):
        if key in self.store:
            self.store[key] = (self.store[key][0], time.time() + ttl)

    async def ttl(self, key):
        item = self.store.get(key)
        return int(item[1] - time.time()) if item else -2

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    async def aclose(self):
        pass


@pytest.fixture
def fake_redis(monkeypatch):
    FakeRedis.store = {}
    import redis.asyncio
    import routers.file_upload
    import shared.job_store
    monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **k: FakeRedis())
    monkeypatch.setattr(routers.file_upload, "_get_redis", lambda: _async(FakeRedis()))
    monkeypatch.setattr(shared.job_store, "_get_redis", lambda: None)  # jobs: this worker's memory
    monkeypatch.setattr(get_settings(), "redis_url", "redis://fake")
    return FakeRedis.store


async def _async(value):
    return value


def _sav_upload(sav: bytes):
    return {"file": ("survey.sav", sav, "application/octet-stream")}


# ── Error envelope ──

def test_errors_have_the_standard_envelope(client, auth_headers, test_sav_bytes):
    r = client.post("/v1/frequency", files=_sav_upload(test_sav_bytes), data={"variable": "gender"})
    assert r.status_code == 401
    body = r.json()
    assert body["success"] is False and body["error"]["code"] and body["error"]["message"]

    r = client.post("/v1/tabulate", headers=auth_headers, files=_sav_upload(test_sav_bytes))  # no spec
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR" and "spec" in body["error"]["message"]

    r = client.post("/v1/tabulate", headers=auth_headers, files=_sav_upload(test_sav_bytes), data={"spec": "{nope"})
    body = r.json()
    assert r.status_code == 400 and body["error"]["code"] == "INVALID_SPEC"
    assert body["detail"]["code"] == "INVALID_SPEC"  # FastAPI's "detail" stays for existing callers

    r = client.get("/v1/jobs/unknown", headers=auth_headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


# ── response_format ──

def test_tabulate_base64_response(client, auth_headers, test_sav_bytes):
    spec = {"banners": ["gender"], "stubs": ["satisfaction"]}
    r = client.post("/v1/tabulate", headers=auth_headers, files=_sav_upload(test_sav_bytes),
                    data={"spec": json.dumps(spec), "response_format": "base64"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    content = base64.b64decode(data["content_base64"])
    assert content[:2] == XLSX_MAGIC and data["size_bytes"] == len(content)
    assert data["filename"].endswith(".xlsx") and data["content_type"].endswith("spreadsheetml.sheet")
    assert data["info"]["stubs_total"] == "1" and data["info"]["stubs_success"] == "1"
    load_workbook(io.BytesIO(content))


def test_default_response_is_the_file(client, auth_headers, test_sav_bytes):
    r = client.post("/v1/convert", headers=auth_headers, files=_sav_upload(test_sav_bytes), data={"target_format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]


def test_unknown_response_format_is_rejected(client, auth_headers, test_sav_bytes):
    r = client.post("/v1/convert", headers=auth_headers, files=_sav_upload(test_sav_bytes),
                    data={"target_format": "csv", "response_format": "pdf"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_url_response_downloads_without_a_key(client, auth_headers, test_sav_bytes, fake_redis):
    r = client.post("/v1/convert", headers=auth_headers, files=_sav_upload(test_sav_bytes),
                    data={"target_format": "csv", "response_format": "url"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["expires_in_seconds"] == 900
    path = data["download_url"].split("://", 1)[1].split("/", 1)[1]
    dl = client.get("/" + path)
    assert dl.status_code == 200 and dl.content.decode("utf-8-sig").startswith("gender")


def test_url_response_without_redis_is_a_clear_error(client, auth_headers, test_sav_bytes):
    r = client.post("/v1/convert", headers=auth_headers, files=_sav_upload(test_sav_bytes),
                    data={"target_format": "csv", "response_format": "url"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "DOWNLOADS_UNAVAILABLE"


# ── File sessions ──

def test_base64_upload_session_lifecycle(client, auth_headers, test_sav_bytes, fake_redis):
    payload = {"filename": "survey.sav", "content_base64": base64.b64encode(test_sav_bytes).decode()}
    r = client.post("/v1/files/upload-base64", headers=auth_headers, json=payload)
    assert r.status_code == 200, r.text
    up = r.json()
    file_id = up["file_id"]
    assert up["n_cases"] == 100 and up["format"] == "sav"

    info = client.get(f"/v1/files/{file_id}", headers=auth_headers).json()["data"]
    assert info["filename"] == "survey.sav" and info["expires_in_seconds"] > 0

    r = client.post("/v1/frequency", headers=auth_headers, data={"file_id": file_id, "variable": "gender"})
    assert r.status_code == 200 and r.json()["data"]["base"] == 100

    assert client.delete(f"/v1/files/{file_id}", headers=auth_headers).json()["data"]["deleted"] is True
    r = client.get(f"/v1/files/{file_id}", headers=auth_headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_multipart_upload_then_tabulate_by_file_id(client, auth_headers, test_sav_bytes, fake_redis):
    file_id = client.post("/v1/files/upload", headers=auth_headers, files=_sav_upload(test_sav_bytes)).json()["file_id"]
    r = client.post("/v1/tabulate", headers=auth_headers,
                    data={"file_id": file_id, "spec": json.dumps({"banners": ["gender"], "stubs": ["satisfaction"]})})
    assert r.status_code == 200 and r.content[:2] == XLSX_MAGIC


def test_upload_rejections(client, auth_headers):
    r = client.post("/v1/files/upload-base64", headers=auth_headers, json={"filename": "a.sav", "content_base64": "%%%"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_BASE64"
    r = client.post("/v1/files/upload-base64", headers=auth_headers,
                    json={"filename": "a.pdf", "content_base64": base64.b64encode(b"x").decode()})
    assert r.status_code == 415 and r.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
    r = client.post("/v1/files/upload", headers=auth_headers, files={"file": ("a.sav", b"not spss", "application/octet-stream")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_FILE"


# ── Async jobs ──

def test_async_tabulate_checks_the_spec_first(client, auth_headers, test_sav_bytes):
    r = client.post("/v1/tabulate", headers=auth_headers, files=_sav_upload(test_sav_bytes),
                    data={"spec": json.dumps({"stubs": ["gender"], "output_mode": "pages"}),
                          "webhook_url": "https://example.com/hook"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_job_store_failure_keeps_the_error_code():
    import asyncio
    from fastapi import HTTPException
    from services.job_runner import run_tabulation_job
    from shared.job_store import JobStore

    store = JobStore()
    job_id = store.create(user_id="Test Key", endpoint="/v1/tabulate")

    async def boom():
        raise HTTPException(400, detail={"code": "VARIABLE_NOT_FOUND", "message": "Stub variables not found: ['x']"})

    loop = asyncio.new_event_loop()  # not asyncio.run: that unsets the loop other tests use
    loop.run_until_complete(run_tabulation_job(job_id, boom))
    loop.close()
    job = store.get(job_id)
    assert job["status"] == "failed" and job["result"]["error"]["code"] == "VARIABLE_NOT_FOUND"
