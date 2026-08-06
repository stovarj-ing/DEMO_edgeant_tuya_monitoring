# Arquitectura de red

## Objetivo

Recolectar periódicamente, desde un **servidor** central, los datos de un medidor
**EdgeAnt** que vive conectado por **WiFi** a un gateway **Alfa Network (OpenWrt)**,
el cual además brinda una salida **HaLow** (802.11ah, sub-GHz) hacia la red del server.

La lectura NO usa la nube Tuya: va por **UDP unicast local** directamente al
dispositivo.

## Topología

```
            red HaLOW (802.11ah)                    red WiFi (2.4 GHz)
   ┌──────────────────────────────┐      ┌──────────────────────────────┐
   │         PC / Server          │      │      EdgeAnt (medidor Tuya)  │
   │   edgeant_monitor.py         │      │  Multi-Circuit Power Meter   │
   │  envia peticiones UDP :4100  │      │  responde unicast UDP        │
   └──────────────┬───────────────┘      └───────────────┬──────────────┘
                  │                                      │
                  │        ┌──────────────┐             │
                  └───────▶│    Alfa GW   │◀────────────┘
                HaLOW      │  (OpenWrt)   │      WiFi
                  UP/LINK   │  br-ahwlan   │   br-lan / AP
                           └──────────────┘
                              bridge / ruteo
                                    │
                                    ▼
                          IP destino: 192.168.1.150
```

### Flujo de una lectura

1. `edgeant_monitor.py` (en el server) crea un `tinytuya.OutletDevice` con
   `device_id`, `device_ip=192.168.1.150`, `local_key` y `version=3.3`.
2. `d.status()` envía un **UDP unicast** al dispositivo a través de la red HaLow,
   el gateway (Alfa) lo encamina hacia su WiFi, y llega al EdgeAnt.
3. El EdgeAnt responde con su mapa de DPs (JSON con los datos eléctricos crudos).
4. El script traduce los DPs (escala) y guarda en CSV + SQLite.

### Dirección del tráfico

- El **server es quien inicia**. Por eso la ruta debe permitir conexiones
  **entrantes** desde el lado HaLow hacia el WiFi: **sin NAT en el medio**.
  (Si el gateway hubiera dejado la interfaz HaLOW como una "WAN" con masquerade,
  el NAT bloquearía las conexiones entrantes no solicitadas → ver `inconvenientes.md`.)

### Servidor como origen de paquetes

El problema / solución del Nav es un punto crítico a validar antes:

- El descubrimiento por **broadcast** (`tinytuya.scan()`, puerto UDP 6666/6667/7000)
  **puede no funcionar** al otro lado del gateway porque el broadcast no siempre se
  reenvía entre interfaces del router.
- El **unicast directo** (`device.status()` hacia la IP del dispositivo) SÍ funciona
  siempre que exista ruta, porque es un simple datagrama punto a punto.

> **Conclusión práctica**: no confiar en el scan para operación; usar unicast.

## Componentes

| Componente | Rol | Interaces |
|------------|-----|-----------|
| PC / Server | Ejecuta `edgeant_monitor.py` | HaLOW (802.11ah) |
| Alfa (OpenWrt) | Gateway/bridge entre HaLOW y WiFi (sin NAT) | br-ahwlan + br-lan |
| EdgeAnt | Medidor Tuya v3.3 que responde peticiones UDP | WiFi (IP fija .150) |

Ver `inconvenientes.md` para el detalle de cada problema y cómo se resolvió.