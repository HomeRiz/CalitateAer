"""Pure helpers that build the national-stations payload for the map card.

This module deliberately imports nothing from Home Assistant so it can be
unit-tested in isolation. Both the sensor platform and (indirectly, via the
exposed entity attributes) the CalitateAer Map Card depend on the shape this
module produces, so it is the single source of truth for that data contract.

Payload shape (the contract the map card reads from
``sensor.rnmca_national_stations`` attributes)::

    {
      "station_count": int,            # stations with valid coordinates
      "with_data_count": int,          # stations that currently have readings/AQI
      "updated": str | None,           # most recent measurement timestamp seen
      "units": {key: unit_str},        # shared once, not repeated per station
      "stations": [
          {
            "id":  location_id,
            "name": str,
            "lat": float,
            "lon": float,
            "net": network_id,
            "aqi": int | None,         # general hourly index code (1-6)
            "t":   str | None,         # measurement timestamp for this station
            "r":   {key: value},       # curated readings, rounded
            "idx": {key: index_code},  # per-parameter specific index (optional)
          },
          ...
      ],
      "attribution": str,
    }

Curated reading keys: pm10, pm25, no2, so2, o3, co, nox, no, benzene, h2s,
nh3, wind_speed, wind_dir, solar, temp, humidity, pressure.
"""
from __future__ import annotations

import re

# Display / iteration priority for curated reading keys.
CURATED_KEYS = [
    "pm10",
    "pm25",
    "no2",
    "so2",
    "o3",
    "co",
    "nox",
    "no",
    "benzene",
    "h2s",
    "nh3",
    "wind_speed",
    "wind_dir",
    "solar",
    "temp",
    "humidity",
    "pressure",
]

_GAS_TOKENS = ("so2", "no2", "nox", "o3", "co", "h2s", "nh3", "no")

_DIACRITICS = {
    "ă": "a",
    "â": "a",
    "î": "i",
    "ș": "s",
    "ş": "s",
    "ț": "t",
    "ţ": "t",
}


def normalize(value) -> str:
    """Lowercase, strip diacritics and collapse whitespace for matching."""
    text = str(value or "").lower()
    for source, target in _DIACRITICS.items():
        text = text.replace(source, target)
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify_parameter(name) -> str | None:
    """Map an RNMCA parameter label to a curated key, or None to skip it."""
    normalized = normalize(name)
    if not normalized:
        return None

    if "pm2" in normalized or "pm 2" in normalized:
        return "pm25"
    if "pm10" in normalized or "pm 10" in normalized:
        return "pm10"
    if ("viteza" in normalized and "vant" in normalized) or "wind speed" in normalized:
        return "wind_speed"
    if (
        (("directia" in normalized or "directie" in normalized) and "vant" in normalized)
        or "wind direction" in normalized
    ):
        return "wind_dir"
    if "radiati" in normalized or "radiation" in normalized or "solar" in normalized:
        return "solar"
    if "temperatur" in normalized or "temperature" in normalized:
        return "temp"
    if "umiditate" in normalized or "humidity" in normalized:
        return "humidity"
    if "presiun" in normalized or "pressure" in normalized:
        return "pressure"

    # Gases and benzene match as exact tokens so "Etilbenzen" (ethylbenzene),
    # "Toluen", xylenes, "Nt", "CS" etc. are NOT misread as a curated parameter.
    token = normalized.replace(" ", "")
    if token in ("benzen", "benzene"):
        return "benzene"
    for key in _GAS_TOKENS:
        if token == key:
            return key
    return None


def _float_or_none(value):
    """Convert a value to float, or return None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rounded(value, digits=2):
    """Round numeric values while preserving None."""
    return None if value is None else round(value, digits)


def _clean_unit(unit) -> str:
    """Best-effort cleanup of mojibake in API unit strings."""
    text = str(unit or "")
    return text.replace("Â", "").strip()


def _latest_group(location_data: dict):
    """Return the most recent simplified timestamp group for a location."""
    groups = location_data.get("locationDataForTimestamps") or []
    return groups[0] if groups else None


def _latest_time(current, candidate):
    """Return the lexicographically latest ISO timestamp-like value."""
    if not candidate:
        return current
    if not current or str(candidate) > str(current):
        return candidate
    return current


def index_locations_data(locations_data) -> dict:
    """Index a recent-data ``locationsData`` list by location id.

    Keys are stored both as the raw id and its string form so callers can look
    up regardless of whether config ids are ints or strings.
    """
    index: dict = {}
    for location in locations_data or []:
        loc_id = location.get("locationId", location.get("id"))
        if loc_id is None:
            continue
        index[loc_id] = location
        index[str(loc_id)] = location
    return index


def build_national_payload(all_locations: dict, locations_data, attribution: str = "") -> dict:
    """Join the national station catalogue with recent data into the card payload.

    ``all_locations`` maps location id -> config ``info`` dict (with latitude,
    longitude, name, networkId). ``locations_data`` is the ``locationsData``
    list from a root (``networkId=1``) recent-data response.
    """
    by_id = index_locations_data(locations_data)
    units: dict = {}
    stations: list = []
    latest_overall = None

    for loc_id, info in all_locations.items():
        info = info or {}
        lat = _float_or_none(info.get("latitude"))
        lon = _float_or_none(info.get("longitude"))
        if lat is None or lon is None:
            continue

        name = info.get("name") or info.get("label") or f"Station {loc_id}"
        network_id = info.get("networkId")

        aqi = None
        timestamp = None
        readings: dict = {}
        specific_index: dict = {}

        live = by_id.get(loc_id)
        if live is None:
            live = by_id.get(str(loc_id))
        if live:
            group = _latest_group(live)
            if group:
                timestamp = group.get("dateTime")
                latest_overall = _latest_time(latest_overall, timestamp)
                general = group.get("hourlyGeneralIndex") or {}
                aqi = general.get("code")
                for value_data in group.get("measurementValuesData", []) or []:
                    if value_data.get("valid", True) is False:
                        continue
                    key = classify_parameter(
                        value_data.get("parameter")
                        or value_data.get("measurementValueName")
                    )
                    if key is None or key in readings:
                        continue
                    value = _float_or_none(
                        value_data.get("usedValue", value_data.get("value"))
                    )
                    if value is None:
                        continue
                    readings[key] = _rounded(value)
                    unit = value_data.get("measurementUnit")
                    if unit and key not in units:
                        units[key] = _clean_unit(unit)
                    code = (value_data.get("hourlySpecificIndex") or {}).get("code")
                    if code is not None:
                        specific_index[key] = code

        station = {
            "id": loc_id,
            "name": name,
            "lat": _rounded(lat, 5),
            "lon": _rounded(lon, 5),
            "net": network_id,
            "aqi": aqi,
            "t": timestamp,
            "r": readings,
        }
        if specific_index:
            station["idx"] = specific_index
        stations.append(station)

    with_data = sum(1 for station in stations if station["r"] or station["aqi"] is not None)
    return {
        "station_count": len(stations),
        "with_data_count": with_data,
        "updated": latest_overall,
        "units": units,
        "stations": stations,
        "attribution": attribution,
    }
