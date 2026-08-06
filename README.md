# EdgeAnt Tuya Monitor

Monitor local del medidor de energía **EdgeAnt "Multi-Circuit Power Meter"** (Tuya,
categoría `cz`), leído por **protocolo Tuya local v3.3** vía `tinytuya`, con
almacenamiento ordenado en CSV + SQLite.

Este repositorio documenta también la **arquitectura de red completa** (servidor →
HaLow → gateway → WiFi → dispositivo), el proceso de puesta en marcha y todos los
**inconvenientes encontrados y resueltos** durante el despliegue.

---

## Contenido

| Ruta | Descripción |
|------|-------------|
| `edgeant_monitor.py` | Script principal: lee el medidor cada N segundos, traduce DPs y guarda CSV + SQLite |
| `config.example.json` | Plantilla de configuración (credenciales NO se versionan) |
| `requirements.txt` | Dependencias Python |
| `assets/arquitectura_halow.png` | Diagrama de la arquitectura de red |
| `docs/arquitectura.md` | Explicación detallada de la arquitectura y flujo de datos |
| `docs/inconvenientes.md` | Problemas encontrados y sus soluciones |
| `scripts/` | Utilidades de descubrimiento (escaneo de puertos Tuya) |

---

## Quick start

```bash
pip install -r requirements.txt

# 1. Copia y llena las credenciales (device_id, device_ip, local_key)
copy config.example.json config.json
# edita config.json con los valores reales

# 2. Ejecuta
python edgeant_monitor.py
```

Alternativa sin archivo: definir variables de entorno.

```bash
set TUYA_DEVICE_ID=...
set TUYA_DEVICE_IP=192.168.1.150
set TUYA_LOCAL_KEY=...
python edgeant_monitor.py
```

> ⚠️ **Seguridad**: `config.json` está en `.gitignore`. Las credenciales Tuya
> (`local_key`) nunca deben subirse al repositorio.

---

## Cómo consigo las credenciales

`device_id`, `device_ip` y `local_key` se obtienen desde la app **Smart Life / Tuya**
o con `tinytuya`:

```bash
python -m tinytuya wizard
```

El `local_key` solo se muestra durante el emparejamiento inicial del dispositivo, así
que guardarlo en ese momento. La IP se puede tomar de la tabla ARP / DHCP del router.

---

## Salidas

- **Consola**: log con cada lectura con nombre y valor (`Lectura OK | corriente_fase_a=0.05, ...`).
- **CSV** (`edgeant_log.csv`): columnas fijas `timestamp_utc, voltaje_fase_a, corriente_fase_a, ...`.
- **SQLite** (`edgeant_data.db`): tabla `readings` con las mismas columnas, consultable:

```python
import sqlite3
conn = sqlite3.connect("edgeant_data.db")
rows = conn.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 10").fetchall()
```

---

## Mapeo de DPs

| DP | Variable | Escala | Unidad |
|----|----------|--------|--------|
| 101 | `voltaje_fase_a` | ×0.1 | V |
| 102 | `corriente_fase_a` | ×0.001 | A |
| 103 | `potencia_fase_a` | ×0.001 | kW |
| 107 | `voltaje_fase_b` | ×0.1 | V |
| 108 | `corriente_fase_b` | ×0.001 | A |
| 109 | `potencia_fase_b` | ×0.001 | kW |
| 113 | `voltaje_fase_c` | ×0.1 | V |
| 114 | `corriente_fase_c` | ×0.001 | A |
| 115 | `potencia_fase_c` | ×0.001 | kW |
| 119 | `frecuencia` | ×1 | Hz |
| 133 | `fase_configurada` | ×1 | — |
| 139 | `modo_fase` | ×1 | — |

Los DPs no catalogados se guardan con su nombre crudo (`dp_<id>`).

---

## Licencia

Proyecto interno/educativo. Usar bajo su propio criterio.