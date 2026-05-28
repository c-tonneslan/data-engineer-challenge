"""Converters from British National Grid (eastings, northings) to WGS84 lat/lng.

Two implementations live here behind a small Protocol so the rest of the
pipeline doesn't care which one is wired up.

- :class:`PyProjConverter` uses the EPSG:27700 (OSGB36 / British National Grid)
  to EPSG:4326 (WGS84) transformation. This is the production-correct path:
  it's deterministic, has no rate limit, and matches what Ordnance Survey
  publish.
- :class:`HTTPConverter` calls https://www.getthedata.com/bng2latlong (the API
  the brief suggests). It's kept around for parity with the brief and for cases
  where pyproj can't be installed, but at the time of writing the endpoint sits
  behind a Cloudflare bot challenge so it can't be hit from a plain script.
  See NOTES.md.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LatLng:
    latitude: float
    longitude: float


class Converter(Protocol):
    def convert(self, easting: int, northing: int) -> LatLng:
        ...


class PyProjConverter:
    """Local BNG -> WGS84 conversion via pyproj.

    Builds the Transformer once and reuses it. always_xy=True keeps the
    coordinate order as (easting, northing) -> (longitude, latitude), which
    is what we want regardless of the axis-order quirks in newer PROJ
    releases.
    """

    def __init__(self) -> None:
        from pyproj import Transformer
        self._t = Transformer.from_crs(
            "EPSG:27700", "EPSG:4326", always_xy=True,
        )

    def convert(self, easting: int, northing: int) -> LatLng:
        lng, lat = self._t.transform(easting, northing)
        return LatLng(latitude=lat, longitude=lng)


class HTTPConverter:
    """BNG -> WGS84 via the getthedata.com bng2latlong API.

    The API itself is fine, but the host now serves Cloudflare's JS challenge
    to non-browser clients, so this path won't work out of the box today.
    Kept here because the brief calls it out and because it's a useful shape
    to keep around: if the API ever goes back to plain JSON, the rest of the
    pipeline doesn't need to change.
    """

    DEFAULT_URL = "https://www.getthedata.com/bng2latlong"

    def __init__(self, session=None, url: str = DEFAULT_URL,
                 timeout: float = 10.0, sleep_s: float = 0.1,
                 max_retries: int = 3):
        if session is None:
            import requests
            session = requests.Session()
            session.headers.setdefault(
                "User-Agent",
                "propeller-data-engineer-challenge/0.1 "
                "(github.com/c-tonneslan/data-engineer-challenge)",
            )
        self._session = session
        self._url = url
        self._timeout = timeout
        self._sleep_s = sleep_s
        self._max_retries = max_retries

    def convert(self, easting: int, northing: int) -> LatLng:
        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                r = self._session.get(
                    self._url,
                    params={"easting": easting, "northing": northing},
                    timeout=self._timeout,
                )
                r.raise_for_status()
                data = r.json()
                status = data.get("status")
                if status != "ok":
                    raise ValueError(
                        f"API returned status={status!r} for "
                        f"easting={easting} northing={northing}: {data!r}"
                    )
                return LatLng(
                    latitude=float(data["latitude"]),
                    longitude=float(data["longitude"]),
                )
            except Exception as e:
                last_err = e
                if attempt == self._max_retries - 1:
                    break
                wait = 2 ** attempt
                log.warning(
                    "retry %d/%d for easting=%s northing=%s: %s (sleep %ss)",
                    attempt + 1, self._max_retries, easting, northing, e, wait,
                )
                time.sleep(wait)
        assert last_err is not None
        raise last_err

    def throttle(self) -> None:
        if self._sleep_s > 0:
            time.sleep(self._sleep_s)
