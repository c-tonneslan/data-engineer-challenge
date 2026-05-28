"""Converter tests.

PyProj is checked against a known landmark (Tower Bridge area), and the HTTP
client is tested with a fake session so we don't hit the network. The
Cloudflare HTML page is one of the failure modes we want to surface clearly.
"""

from __future__ import annotations

import json

import pytest

from data_engineer_challenge.converters import (
    HTTPConverter, LatLng, PyProjConverter,
)


class _FakeResponse:
    def __init__(self, payload, status_code=200, raises=None):
        self._payload = payload
        self.status_code = status_code
        self._raises = raises

    def raise_for_status(self):
        if self._raises:
            raise self._raises

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        return self._responses.pop(0)


def test_pyproj_converts_tower_bridge_area_to_central_london():
    c = PyProjConverter()
    ll = c.convert(533630, 180220)
    # Tolerant bounds: BNG 533630, 180220 is in central London. Anything
    # outside ~0.01 degrees would mean the transform is wired up wrong.
    assert isinstance(ll, LatLng)
    assert 51.50 < ll.latitude < 51.52
    assert -0.09 < ll.longitude < -0.06


def test_pyproj_converts_edinburgh_to_55ish_north():
    c = PyProjConverter()
    ll = c.convert(325000, 673500)
    assert 55.9 < ll.latitude < 56.0
    assert -3.3 < ll.longitude < -3.1


def test_http_converter_returns_latlng_on_ok_status():
    session = _FakeSession([
        _FakeResponse({
            "status": "ok",
            "easting": 530000, "northing": 180000,
            "latitude": 51.4778, "longitude": -0.0014,
        }),
    ])
    c = HTTPConverter(session=session, sleep_s=0, max_retries=1)
    ll = c.convert(530000, 180000)
    assert ll == LatLng(latitude=51.4778, longitude=-0.0014)
    assert session.calls[0][1] == {"easting": 530000, "northing": 180000}


def test_http_converter_raises_on_non_ok_status():
    session = _FakeSession([
        _FakeResponse({"status": "error", "error": "outside grid"}),
    ])
    c = HTTPConverter(session=session, sleep_s=0, max_retries=1)
    with pytest.raises(ValueError, match="error"):
        c.convert(1, 1)


def test_http_converter_retries_then_succeeds():
    session = _FakeSession([
        _FakeResponse({"status": "error"}),
        _FakeResponse({"status": "error"}),
        _FakeResponse({
            "status": "ok", "latitude": 51.5, "longitude": -0.1,
        }),
    ])
    c = HTTPConverter(session=session, sleep_s=0, max_retries=3)
    # Patch out sleep so the test runs instantly.
    import data_engineer_challenge.converters as mod
    mod.time.sleep = lambda *_: None
    ll = c.convert(530000, 180000)
    assert ll.latitude == 51.5
    assert len(session.calls) == 3


def test_http_converter_gives_up_after_max_retries():
    session = _FakeSession([
        _FakeResponse({"status": "error"}),
        _FakeResponse({"status": "error"}),
    ])
    c = HTTPConverter(session=session, sleep_s=0, max_retries=2)
    import data_engineer_challenge.converters as mod
    mod.time.sleep = lambda *_: None
    with pytest.raises(ValueError):
        c.convert(1, 1)
    assert len(session.calls) == 2


def test_http_converter_treats_html_response_as_failure():
    """If the API is fronted by a Cloudflare challenge, response.json() raises
    JSONDecodeError. The converter should surface that as a hard failure,
    not silently return garbage."""
    err = json.JSONDecodeError("Expecting value", "<!DOCTYPE html>", 0)
    session = _FakeSession([_FakeResponse(err)])
    c = HTTPConverter(session=session, sleep_s=0, max_retries=1)
    with pytest.raises(json.JSONDecodeError):
        c.convert(530000, 180000)
