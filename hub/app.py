"""
Dashboard Connector - Hub

Recibe los latidos (heartbeat) de los agentes instalados en cada equipo y
expone un panel para ver quien esta compartiendo recursos y cambiar su modo.

Modos por equipo:
  off          - fuera del pool, no comparte nada
  receive_only - solo recibe trabajo (ejecuta), no reparte
  send_only    - solo envia trabajo, no ejecuta nada
  full         - envia y recibe

El hub NUNCA manda comandos arbitrarios al agente: solo publica el modo
deseado. Es el agente quien decide que hacer con el, en local.
"""

import os
import sqlite3
import time
import json
from contextlib import closing

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("DC_DB_PATH", "/data/hub.db")
AGENT_TOKEN = os.environ.get("DC_AGENT_TOKEN", "")
ADMIN_TOKEN = os.environ.get("DC_ADMIN_TOKEN", "")
POLL_INTERVAL = int(os.environ.get("DC_POLL_INTERVAL", "20"))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

MODES = ("off", "receive_only", "send_only", "full")

if not AGENT_TOKEN or not ADMIN_TOKEN:
    raise SystemExit(
        "Faltan DC_AGENT_TOKEN y/o DC_ADMIN_TOKEN en el entorno. "
        "Genera dos tokens distintos antes de arrancar el hub."
    )

app = FastAPI(title="Dashboard Connector Hub", docs_url=None, redoc_url=None)


SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id       TEXT PRIMARY KEY,
    hostname      TEXT,
    os            TEXT,
    os_detail     TEXT,
    ip            TEXT,
    cpu_cores     INTEGER,
    cpu_pct       REAL,
    ram_total_mb  INTEGER,
    ram_used_mb   INTEGER,
    disk_total_gb REAL,
    disk_used_gb  REAL,
    gpu           TEXT,
    docker        TEXT,
    agent_version TEXT,
    share_cpu_pct INTEGER,
    share_ram_mb  INTEGER,
    desired_mode  TEXT DEFAULT 'off',
    applied_mode  TEXT,
    first_seen    INTEGER,
    last_seen     INTEGER,
    notes         TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER,
    node_id TEXT,
    kind    TEXT,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
"""


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(db()) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def log_event(conn, node_id, kind, detail=""):
    conn.execute(
        "INSERT INTO events (ts, node_id, kind, detail) VALUES (?,?,?,?)",
        (int(time.time()), node_id, kind, detail),
    )


def require(token_value, expected, what):
    # Comparacion de longitud constante para no filtrar el token por tiempos.
    if not token_value or not expected:
        raise HTTPException(status_code=401, detail=f"Falta token de {what}")
    given = token_value.removeprefix("Bearer ").strip()
    import hmac

    if not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail=f"Token de {what} invalido")


class Heartbeat(BaseModel):
    node_id: str = Field(min_length=1, max_length=120)
    hostname: str = ""
    os: str = ""
    os_detail: str = ""
    cpu_cores: int = 0
    cpu_pct: float | None = None
    ram_total_mb: int = 0
    ram_used_mb: int = 0
    disk_total_gb: float = 0
    disk_used_gb: float = 0
    gpu: str = ""
    docker: str = ""
    agent_version: str = ""
    share_cpu_pct: int = 0
    share_ram_mb: int = 0
    applied_mode: str = "off"


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/v1/heartbeat")
def heartbeat(hb: Heartbeat, request: Request, authorization: str = Header(default="")):
    require(authorization, AGENT_TOKEN, "agente")
    now = int(time.time())
    ip = request.client.host if request.client else ""
    # Respeta X-Forwarded-For si el hub va detras de un proxy inverso.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        ip = fwd.split(",")[0].strip()

    with closing(db()) as conn:
        row = conn.execute(
            "SELECT desired_mode, applied_mode FROM nodes WHERE node_id=?", (hb.node_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO nodes (node_id, desired_mode, first_seen) VALUES (?,?,?)",
                (hb.node_id, "off", now),
            )
            log_event(conn, hb.node_id, "alta", f"nuevo equipo desde {ip}")
            desired = "off"
        else:
            desired = row["desired_mode"] or "off"
            if row["applied_mode"] != hb.applied_mode:
                log_event(
                    conn,
                    hb.node_id,
                    "modo_aplicado",
                    f"{row['applied_mode']} -> {hb.applied_mode}",
                )

        conn.execute(
            """UPDATE nodes SET hostname=?, os=?, os_detail=?, ip=?, cpu_cores=?, cpu_pct=?,
                   ram_total_mb=?, ram_used_mb=?, disk_total_gb=?, disk_used_gb=?, gpu=?,
                   docker=?, agent_version=?, share_cpu_pct=?, share_ram_mb=?,
                   applied_mode=?, last_seen=?
               WHERE node_id=?""",
            (
                hb.hostname, hb.os, hb.os_detail, ip, hb.cpu_cores, hb.cpu_pct,
                hb.ram_total_mb, hb.ram_used_mb, hb.disk_total_gb, hb.disk_used_gb,
                hb.gpu, hb.docker, hb.agent_version, hb.share_cpu_pct, hb.share_ram_mb,
                hb.applied_mode, now, hb.node_id,
            ),
        )
        conn.commit()

    return {"desired_mode": desired, "poll_interval": POLL_INTERVAL}


def node_to_dict(r, now):
    online = r["last_seen"] is not None and (now - r["last_seen"]) < (POLL_INTERVAL * 3)
    d = dict(r)
    d["online"] = online
    d["seen_ago"] = (now - r["last_seen"]) if r["last_seen"] else None
    # Lo que este equipo aporta ahora mismo al pool.
    sharing = online and d["applied_mode"] in ("receive_only", "full")
    d["sharing"] = sharing
    cores = d["cpu_cores"] or 0
    d["offer_cores"] = round(cores * (d["share_cpu_pct"] or 0) / 100, 1) if sharing else 0
    d["offer_ram_mb"] = (d["share_ram_mb"] or 0) if sharing else 0
    return d


@app.get("/api/v1/nodes")
def list_nodes(authorization: str = Header(default="")):
    require(authorization, ADMIN_TOKEN, "admin")
    now = int(time.time())
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM nodes ORDER BY hostname, node_id").fetchall()
        events = conn.execute(
            "SELECT ts, node_id, kind, detail FROM events ORDER BY id DESC LIMIT 40"
        ).fetchall()

    nodes = [node_to_dict(r, now) for r in rows]
    pool = {
        "nodes_total": len(nodes),
        "nodes_online": sum(1 for n in nodes if n["online"]),
        "nodes_sharing": sum(1 for n in nodes if n["sharing"]),
        "cores_offered": round(sum(n["offer_cores"] for n in nodes), 1),
        "ram_offered_gb": round(sum(n["offer_ram_mb"] for n in nodes) / 1024, 1),
        "poll_interval": POLL_INTERVAL,
    }
    return {"pool": pool, "nodes": nodes, "events": [dict(e) for e in events]}


class ModeChange(BaseModel):
    mode: str


@app.post("/api/v1/nodes/{node_id}/mode")
def set_mode(node_id: str, body: ModeChange, authorization: str = Header(default="")):
    require(authorization, ADMIN_TOKEN, "admin")
    if body.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Modo invalido. Validos: {MODES}")
    with closing(db()) as conn:
        cur = conn.execute(
            "UPDATE nodes SET desired_mode=? WHERE node_id=?", (body.mode, node_id)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Equipo desconocido")
        log_event(conn, node_id, "modo_pedido", body.mode)
        conn.commit()
    return {"ok": True, "node_id": node_id, "desired_mode": body.mode}


class NoteChange(BaseModel):
    notes: str = ""


@app.post("/api/v1/nodes/{node_id}/notes")
def set_notes(node_id: str, body: NoteChange, authorization: str = Header(default="")):
    require(authorization, ADMIN_TOKEN, "admin")
    with closing(db()) as conn:
        conn.execute("UPDATE nodes SET notes=? WHERE node_id=?", (body.notes[:300], node_id))
        conn.commit()
    return {"ok": True}


@app.delete("/api/v1/nodes/{node_id}")
def forget_node(node_id: str, authorization: str = Header(default="")):
    require(authorization, ADMIN_TOKEN, "admin")
    with closing(db()) as conn:
        conn.execute("DELETE FROM nodes WHERE node_id=?", (node_id,))
        log_event(conn, node_id, "baja", "eliminado desde el panel")
        conn.commit()
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
