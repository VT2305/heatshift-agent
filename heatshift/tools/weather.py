from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import httpx

from ..models import HeatReading
from ..store import load_site_state

BASE = Path(__file__).resolve().parents[2]
CACHE_FILE = BASE / "data" / "last_live_heat.json"
NEA_WBGT_URL = "https://api-open.data.gov.sg/v2/real-time/api/weather"


def _band(wbgt: float) -> str:
    if wbgt < 31:
        return "under_31"
    if wbgt < 32:
        return "31_to_under_32"
    if wbgt < 33:
        return "32_to_under_33"
    return "33_and_above"


def _walk(obj):
    """Yield nested dicts/lists for schema-tolerant parsing."""
    yield obj
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)


def _extract_wbgt(payload: dict) -> tuple[float, str, datetime]:
    """
    data.gov.sg's weather sub-API can evolve its envelope. We deliberately
    parse by semantic keys inside the documented data.records/item/readings
    structure rather than assuming one brittle JSON path.
    """
    candidates = []
    timestamp = None
    station = "NEA"

    for node in _walk(payload):
        if not isinstance(node, dict):
            continue

        for key in ("timestamp", "datetime", "dateTime"):
            if key in node and isinstance(node[key], str):
                try:
                    timestamp = datetime.fromisoformat(node[key].replace("Z", "+00:00"))
                except Exception:
                    pass

        for skey in ("station_id", "stationId", "id", "name"):
            if skey in node and isinstance(node[skey], str) and len(node[skey]) < 80:
                station = node[skey]

        # Common reading shapes: {"value": 32.1}, {"wbgt": 32.1},
        # or a key containing "wbgt".
        for key, value in node.items():
            key_l = str(key).lower()
            if isinstance(value, (int, float)):
                if "wbgt" in key_l:
                    candidates.append(float(value))
                elif key_l in {"value", "reading"} and 15 <= float(value) <= 50:
                    candidates.append(float(value))

    if not candidates:
        raise ValueError("No WBGT numeric reading found in live response")

    # Singapore WBGT is a Celsius-like index; select the latest plausible value.
    wbgt = candidates[-1]
    return wbgt, station, timestamp or datetime.now().astimezone()


def get_live_heat_state(timeout_seconds: float = 4.0) -> HeatReading:
    headers = {"Accept": "application/json"}
    key = os.getenv("DATA_GOV_SG_API_KEY")
    if key:
        headers["x-api-key"] = key

    response = httpx.get(
        NEA_WBGT_URL,
        params={"api": "wbgt"},
        headers=headers,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    wbgt, station, ts = _extract_wbgt(payload)

    reading = HeatReading(
        timestamp=ts,
        source="NEA_WBGT",
        station_id=station,
        wbgt_c=round(wbgt, 1),
        heat_band=_band(wbgt),
        is_simulated_forecast=False,
    )
    CACHE_FILE.write_text(json.dumps(reading.model_dump(mode="json"), indent=2), encoding="utf-8")
    return reading


def get_cached_heat_state() -> HeatReading | None:
    if not CACHE_FILE.exists():
        return None
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        raw["source"] = "CACHED_NEA_WBGT"
        return HeatReading(**raw)
    except Exception:
        return None


def get_heat_state(
    use_simulated: bool = True,
    scenario_index: int = 2,
    prefer_live: bool = False,
) -> HeatReading:
    if prefer_live and not use_simulated:
        try:
            return get_live_heat_state()
        except Exception:
            cached = get_cached_heat_state()
            if cached is not None:
                return cached

    state = load_site_state()
    reading = state.heat_series[min(max(scenario_index, 0), len(state.heat_series)-1)]
    if use_simulated:
        return reading

    cached = get_cached_heat_state()
    if cached is not None:
        return cached

    # Never fake "live": the final fallback is explicitly simulated.
    return HeatReading(
        timestamp=datetime.now().astimezone(),
        source="SIMULATED",
        station_id="demo-fallback",
        wbgt_c=reading.wbgt_c,
        heat_band=_band(reading.wbgt_c),
        is_simulated_forecast=True,
    )
