"""Parsed-data cache (services/data_cache.py) and the library file download the Dataset step uses."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import get_settings
from services import data_cache
from services.data_loader import codebook_from_spss, load_data


@pytest.fixture(autouse=True)
def fresh_cache():
    data_cache.clear()
    yield
    data_cache.clear()


def test_same_file_is_parsed_once_and_each_caller_gets_its_own_copy(test_sav_bytes):
    first = data_cache.load_data_cached(test_sav_bytes, "t.sav")
    first.df["_total_"] = 1.0                      # tabulation adds columns to the data it's given
    first.meta.variable_value_labels["_total_"] = {1.0: "Total"}
    second = data_cache.load_data_cached(test_sav_bytes, "t.sav")
    assert data_cache.stats == {"hits": 1, "misses": 1}
    assert "_total_" not in second.df.columns and "_total_" not in second.meta.variable_value_labels
    assert second.df.equals(load_data(test_sav_bytes, "t.sav").df)


def test_a_different_codebook_is_a_different_entry(test_sav_bytes):
    data = load_data(test_sav_bytes, "t.sav")
    cb = codebook_from_spss(test_sav_bytes, data, "t.sav")
    data_cache.load_data_cached(test_sav_bytes, "t.sav")
    data_cache.load_data_cached(test_sav_bytes, "t.sav", cb)
    data_cache.load_data_cached(test_sav_bytes, "t.sav", cb)
    assert data_cache.stats == {"hits": 1, "misses": 2}


def test_zero_budget_turns_the_cache_off(test_sav_bytes, monkeypatch):
    monkeypatch.setattr(get_settings(), "parsed_cache_mb", 0)
    data_cache.load_data_cached(test_sav_bytes, "t.sav")
    data_cache.load_data_cached(test_sav_bytes, "t.sav")
    assert data_cache.stats == {"hits": 0, "misses": 0}


def test_library_file_download_is_owner_only(auth_headers, monkeypatch):
    """GET /v1/library/{id}/file returns the stored bytes to the file's owner, 403 to anyone else."""
    from routers.library import router
    from services.library_service import LibraryService

    files = {"mine": {"user_id": "Test Key", "filename": "wave 2.sav"}, "theirs": {"user_id": "someone else", "filename": "x.sav"}}

    async def meta(self, library_id):
        return files.get(library_id)

    async def download(self, library_id):
        return b"SAVBYTES", files[library_id]["filename"]

    monkeypatch.setattr(LibraryService, "__init__", lambda self: None)
    monkeypatch.setattr(LibraryService, "get_file_metadata", meta)
    monkeypatch.setattr(LibraryService, "download_file", download)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    ok = c.get("/v1/library/mine/file", headers=auth_headers)
    assert ok.status_code == 200 and ok.content == b"SAVBYTES"
    assert "wave%202.sav" in ok.headers["content-disposition"]
    assert c.get("/v1/library/theirs/file", headers=auth_headers).status_code == 403
    assert c.get("/v1/library/gone/file", headers=auth_headers).status_code == 404
    assert c.get("/v1/library/mine/file").status_code in (401, 403)
