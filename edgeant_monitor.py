"""Monitor ordenado del medidor EdgeAnt (Tuya) por UDP unicast local.

Conecta al medidor "Multi-Circuit Power Meter" (Tuya, categoria cz) via
tinytuya (protocolo v3.3), lee los DPs crudos, los traduce a variables
legibles y los almacena ordenadamente en CSV + SQLite.

Las credenciales NO estan hardcodeadas: se leen de config.json (ver
config.example.json) o de variables de entorno:
    TUYA_DEVICE_ID, TUYA_DEVICE_IP, TUYA_LOCAL_KEY
"""

from __future__ import annotations

import csv
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import tinytuya

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

CONFIG_FILE = Path(__file__).with_name("config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "device_id": "",
    "device_ip": "",
    "local_key": "",
    "protocol_version": 3.3,
    "socket_timeout_seconds": 5,
    "poll_interval_seconds": 5,
    "max_consecutive_failures_before_backoff": 3,
    "backoff_seconds": 30,
    "csv_path": "edgeant_log.csv",
    "sqlite_path": "edgeant_data.db",
    "log_path": "edgeant_monitor.log",
}

# DP -> (nombre_legible, factor_escala, unidad)
DP_MAP: dict[str, tuple[str, float, str]] = {
    "101": ("voltaje_fase_a", 0.1, "V"),
    "102": ("corriente_fase_a", 0.001, "A"),
    "103": ("potencia_fase_a", 0.001, "kW"),
    "107": ("voltaje_fase_b", 0.1, "V"),
    "108": ("corriente_fase_b", 0.001, "A"),
    "109": ("potencia_fase_b", 0.001, "kW"),
    "113": ("voltaje_fase_c", 0.1, "V"),
    "114": ("corriente_fase_c", 0.001, "A"),
    "115": ("potencia_fase_c", 0.001, "kW"),
    "119": ("frecuencia", 1, "Hz"),
    "133": ("fase_configurada", 1, ""),
    "139": ("modo_fase", 1, ""),
}

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def setup_logging(log_path: str) -> logging.Logger:
    logger = logging.getLogger("edgeant")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger

# ---------------------------------------------------------------------------
# CONFIG: config.json -> env vars -> defaults
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config.update(json.load(f))

    config["device_id"] = os.environ.get("TUYA_DEVICE_ID", config["device_id"])
    config["device_ip"] = os.environ.get("TUYA_DEVICE_IP", config["device_ip"])
    config["local_key"] = os.environ.get("TUYA_LOCAL_KEY", config["local_key"])

    if not config["device_id"] or not config["device_ip"] or not config["local_key"]:
        sys.exit(
            "ERROR: faltan credenciales. Copia config.example.json a config.json "
            "y llenalo, o define TUYA_DEVICE_ID/TUYA_DEVICE_IP/TUYA_LOCAL_KEY."
        )
    return config

# ---------------------------------------------------------------------------
# TRADUCCIÓN DE DPs -> VALORES NOMBRADOS
# ---------------------------------------------------------------------------

def translate_dps(raw_dps: dict[str, Any]) -> dict[str, Any]:
    """Convierte DPs crudos a nombres legibles con su escala/unidad."""
    out: dict[str, Any] = {}
    for dp_id, raw in raw_dps.items():
        info = DP_MAP.get(dp_id)
        if info:
            name, scale, _unit = info
            try:
                out[name] = round(float(raw) * scale, 3)
            except (TypeError, ValueError):
                out[name] = raw
        else:
            out[f"dp_{dp_id}"] = raw
    return out

# ---------------------------------------------------------------------------
# ALMACENAMIENTO ORDENADO (CSV + SQLite)
# ---------------------------------------------------------------------------

class Storage:
    def __init__(self, field_names: list[str], csv_path: str, sqlite_path: str):
        self.field_names = field_names
        self.csv_path = csv_path
        self.sqlite_path = sqlite_path
        self._init_csv()
        self._init_sqlite()

    def _init_csv(self) -> None:
        self._csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        if Path(self.csv_path).stat().st_size == 0:
            self._csv_writer.writerow(["timestamp_utc"] + self.field_names)
            self._csv_file.flush()

    def _init_sqlite(self) -> None:
        cols = ", ".join(f'"{c}" REAL' for c in self.field_names)
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS readings ('
                f'id INTEGER PRIMARY KEY AUTOINCREMENT, '
                f'timestamp_utc TEXT NOT NULL, {cols})'
            )
            conn.commit()

    def save(self, ts: str, values: dict[str, Any]) -> None:
        row = [values.get(c, "") for c in self.field_names]

        self._csv_writer.writerow([ts] + row)
        self._csv_file.flush()

        ph = ", ".join("?" for _ in self.field_names)
        cols = ", ".join(f'"{c}"' for c in self.field_names)
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                f'INSERT INTO readings (timestamp_utc, {cols}) VALUES (?, {ph})',
                [ts] + row,
            )
            conn.commit()

    def close(self) -> None:
        self._csv_file.close()

# ---------------------------------------------------------------------------
# CLIENTE DEL DISPOSITIVO
# ---------------------------------------------------------------------------

class EdgeAnt:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._dev = self._build()

    def _build(self) -> tinytuya.OutletDevice:
        d = tinytuya.OutletDevice(
            self.config["device_id"],
            self.config["device_ip"],
            self.config["local_key"],
        )
        d.set_version(self.config["protocol_version"])
        d.set_socketTimeout(self.config["socket_timeout_seconds"])
        return d

    def read(self) -> Optional[dict[str, Any]]:
        try:
            data = self._dev.status()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Excepción en lectura: %s", exc)
            return None
        if not data or "dps" not in data or "Error" in data:
            return None
        return data["dps"]

    def reconnect(self) -> None:
        self.logger.info("Reconstruyendo conexión...")
        self._dev = self._build()

# ---------------------------------------------------------------------------
# LOOP PRINCIPAL
# ---------------------------------------------------------------------------

def main() -> None:
    config = load_config()
    logger = setup_logging(config["log_path"])
    device = EdgeAnt(config, logger)
    storage = Storage(
        [name for name, _s, _u in DP_MAP.values()],
        config["csv_path"],
        config["sqlite_path"],
    )
    shutdown = False

    def handle_signal(_signum, _frame):  # noqa: ANN001
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("=== Iniciando monitor EdgeAnt ===")
    logger.info("Dispositivo %s @ %s (v%s)", config["device_id"], config["device_ip"], config["protocol_version"])
    logger.info("CSV: %s | SQLite: %s", config["csv_path"], config["sqlite_path"])

    consecutive_failures = 0

    try:
        while not shutdown:
            raw_dps = device.read()

            if raw_dps is None:
                consecutive_failures += 1
                logger.warning("Fallo de lectura #%d consecutivo", consecutive_failures)
                if consecutive_failures >= config["max_consecutive_failures_before_backoff"]:
                    logger.error(
                        "Demasiados fallos (%d). Reintentando en %d s...",
                        consecutive_failures,
                        config["backoff_seconds"],
                    )
                    device.reconnect()
                    time.sleep(config["backoff_seconds"])
                    consecutive_failures = 0
                else:
                    time.sleep(config["poll_interval_seconds"])
                continue

            consecutive_failures = 0
            values = translate_dps(raw_dps)
            ts = datetime.now(timezone.utc).isoformat()
            storage.save(ts, values)

            resumen = ", ".join(f"{k}={v}" for k, v in sorted(values.items()))
            logger.info("Lectura OK | %s", resumen)

            time.sleep(config["poll_interval_seconds"])

    finally:
        storage.close()
        logger.info("=== Monitor detenido ===")


if __name__ == "__main__":
    main()
