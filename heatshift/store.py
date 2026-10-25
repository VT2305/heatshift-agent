from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .models import SiteState, WorkPlan

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
DB = DATA / "heatshift.db"


def load_site_state() -> SiteState:
    workers = json.loads((DATA / "workers.json").read_text())
    tasks = json.loads((DATA / "tasks.json").read_text())
    heat = json.loads((DATA / "demo_heat_scenario.json").read_text())
    current = json.loads((DATA / "current_plan.json").read_text())
    return SiteState(
        site_id="SITE-A",
        workers=workers,
        tasks=tasks,
        current_plan=current,
        heat_series=heat,
    )


def save_current_plan(plan: WorkPlan) -> None:
    (DATA / "current_plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2)
    )


def init_db() -> None:
    con = sqlite3.connect(DB)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event TEXT NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        con.commit()
    finally:
        con.close()


def audit(event: str, payload: dict) -> None:
    init_db()
    con = sqlite3.connect(DB)
    try:
        con.execute(
            "INSERT INTO audit_log(ts,event,payload) VALUES(?,?,?)",
            (datetime.now(timezone.utc).isoformat(), event, json.dumps(payload, default=str)),
        )
        con.commit()
    finally:
        con.close()


def read_audit(limit: int = 100) -> list[dict]:
    init_db()
    con = sqlite3.connect(DB)
    try:
        rows = con.execute(
            "SELECT ts,event,payload FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"ts": ts, "event": event, "payload": json.loads(payload)}
            for ts, event, payload in rows
        ]
    finally:
        con.close()
