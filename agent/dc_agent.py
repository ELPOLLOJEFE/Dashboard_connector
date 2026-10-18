#!/usr/bin/env python3
"""
Dashboard Connector - Agente

Se instala en cada equipo que vaya a compartir (o no) recursos.
Cada X segundos manda al hub: CPU, RAM, disco, SO, y cuanto ofrece.
El hub le responde con el modo deseado y el agente lo aplica en local.

Lo que el agente NO hace, a proposito:
  - no ejecuta comandos que vengan del hub
  - no abre ningun puerto de escucha
  - solo sale hacia el hub por HTTP(S)

Dependencias: ninguna obligatoria (stdlib).
  psutil es opcional y mejora la lectura de CPU, sobre todo en Windows.
"""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0.0"

HUB_URL = os.environ.get("DC_HUB_URL", "").rstrip("/")
TOKEN = os.environ.get("DC_AGENT_TOKEN", "")
NODE_ID = os.environ.get("DC_NODE_ID") or socket.gethostname().lower()
INTERVAL = int(os.environ.get("DC_INTERVAL", "20"))
SHARE_CPU_PCT = int(os.environ.get("DC_SHARE_CPU_PCT", "50"))
SHARE_RAM_MB = int(os.environ.get("DC_SHARE_RAM_MB", "2048"))
STATE_DIR = os.environ.get("DC_STATE_DIR") or (
    r"C:\ProgramData\dashboard-connector" if os.name == "nt" else "/var/lib/dashboard-connector"
)
# Servicio local que se arranca/para segun el modo. Vacio = no tocar nada.
WORKER_UNIT = os.environ.get("DC_WORKER_UNIT", "")
VERIFY_TLS = os.environ.get("DC_VERIFY_TLS", "1") != "0"

IS_WIN = os.name == "nt"

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- metricas

_prev_cpu = {}


def cpu_percent():
    if psutil:
        return round(psutil.cpu_percent(interval=1.0), 1)
    if not IS_WIN:
        try:
            def read():
                with open("/proc/stat") as f:
                    parts = f.readline().split()[1:]
                vals = [int(v) for v in parts]
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
                return sum(vals), idle

            t1, i1 = read()
            time.sleep(1.0)
            t2, i2 = read()
            dt, di = t2 - t1, i2 - i1
            return round(100.0 * (dt - di) / dt, 1) if dt > 0 else None
        except Exception:
            return None
    return None  # en Windows sin psutil no estimamos CPU


def cpu_cores():
    return os.cpu_count() or 0


def mem_mb():
    """Devuelve (total_mb, usado_mb)."""
    if psutil:
        m = psutil.virtual_memory()
        return int(m.total / 1048576), int((m.total - m.available) / 1048576)
    if IS_WIN:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        total = int(st.ullTotalPhys / 1048576)
        return total, total - int(st.ullAvailPhys / 1048576)
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, v = line.partition(":")
            info[k] = int(v.split()[0])  # kB
    total = info.get("MemTotal", 0) // 1024
    avail = info.get("MemAvailable", 0) // 1024
    return total, total - avail


def disk_gb():
    path = "C:\\" if IS_WIN else "/"
    try:
        u = shutil.disk_usage(path)
        return round(u.total / 1073741824, 1), round(u.used / 1073741824, 1)
    except Exception:
        return 0.0, 0.0


def run(cmd):
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=8,
            creationflags=0x08000000 if IS_WIN else 0,  # sin ventana en Windows
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def detect_docker():
    if not shutil.which("docker"):
        return ""
    ver = run(["docker", "version", "--format", "{{.Server.Version}}"])
    if not ver:
        return "instalado (sin acceso al demonio)"
    swarm = run(["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"])
    return f"{ver}" + (f" / swarm:{swarm}" if swarm and swarm != "inactive" else "")


def detect_gpu():
    if not shutil.which("nvidia-smi"):
        return ""
    out = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    return out.splitlines()[0].strip() if out else ""


def os_detail():
    if IS_WIN:
        return f"{platform.system()} {platform.release()} {platform.version()}"
    try:
        pretty = ""
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    pretty = line.split("=", 1)[1].strip().strip('"')
        return pretty or platform.platform()
    except Exception:
        return platform.platform()


# ------------------------------------------------------------ aplicar modo


def state_file():
    return os.path.join(STATE_DIR, "mode")


def write_state(mode):
    """Deja el modo en un fichero para que cualquier worker local lo lea."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = state_file() + ".tmp"
        with open(tmp, "w") as f:
            f.write(mode + "\n")
        os.replace(tmp, state_file())
    except Exception as e:
        log(f"aviso: no se pudo escribir el estado en {STATE_DIR}: {e}")


def control_worker(should_run):
    """Arranca o para el servicio local de trabajo, si hay uno configurado."""
    if not WORKER_UNIT:
        return
    action = "start" if should_run else "stop"
    if IS_WIN:
        run(["sc", action, WORKER_UNIT])
    else:
        run(["systemctl", action, WORKER_UNIT])


def apply_mode(mode, current):
    if mode == current:
        return current
    log(f"cambio de modo: {current} -> {mode}")
    write_state(mode)
    # Solo ejecuta trabajo ajeno quien recibe.
    control_worker(mode in ("receive_only", "full"))
    return mode


# ------------------------------------------------------------------ latido


def send_heartbeat(payload):
    req = urllib.request.Request(
        f"{HUB_URL}/api/v1/heartbeat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        method="POST",
    )
    ctx = None
    if not VERIFY_TLS:
        import ssl

        ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return json.loads(r.read().decode())


def main():
    if not HUB_URL or not TOKEN:
        sys.exit("ERROR: faltan DC_HUB_URL y/o DC_AGENT_TOKEN en el entorno.")

    log(f"agente {VERSION} | equipo={NODE_ID} | hub={HUB_URL} | cada {INTERVAL}s")
    current_mode = "off"
    if os.path.exists(state_file()):
        try:
            with open(state_file()) as f:
                current_mode = f.read().strip() or "off"
        except Exception:
            pass

    interval = INTERVAL
    fails = 0
    while True:
        try:
            total_mb, used_mb = mem_mb()
            dtotal, dused = disk_gb()
            payload = {
                "node_id": NODE_ID,
                "hostname": socket.gethostname(),
                "os": platform.system(),
                "os_detail": os_detail(),
                "cpu_cores": cpu_cores(),
                "cpu_pct": cpu_percent(),
                "ram_total_mb": total_mb,
                "ram_used_mb": used_mb,
                "disk_total_gb": dtotal,
                "disk_used_gb": dused,
                "gpu": detect_gpu(),
                "docker": detect_docker(),
                "agent_version": VERSION,
                "share_cpu_pct": SHARE_CPU_PCT,
                "share_ram_mb": SHARE_RAM_MB,
                "applied_mode": current_mode,
            }
            resp = send_heartbeat(payload)
            fails = 0
            new_interval = int(resp.get("poll_interval") or INTERVAL)
            if new_interval != interval:
                log(f"el hub fija el latido en {new_interval}s")
                interval = new_interval
            prev = current_mode
            current_mode = apply_mode(resp.get("desired_mode", "off"), current_mode)
            if current_mode != prev:
                # Confirma el cambio al hub enseguida, para que el panel no se
                # quede un latido entero mostrando "pedido" en vez de "aplicado".
                time.sleep(1)
                continue
        except urllib.error.HTTPError as e:
            fails += 1
            log(f"hub respondio {e.code}: {e.reason}")
        except Exception as e:
            fails += 1
            log(f"sin contacto con el hub: {e}")

        # Si el hub no responde, espaciamos los intentos hasta 5 minutos.
        wait = min(interval * (2 ** min(fails, 4)), 300) if fails else interval
        time.sleep(wait)


if __name__ == "__main__":
    main()
