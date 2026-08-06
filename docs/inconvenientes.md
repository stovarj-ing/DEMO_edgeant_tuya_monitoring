# Inconvenientes encontrados y soluciones

Bitácora de los problemas reales que se presentaron durante la puesta en marcha,
en el orden en que ocurrieron.

---

## 1. El EdgeAnt no respondía al scanner (`tinytuya.scan()` → 0 dispositivos)

**Síntoma**
- El scan por broadcast (`python -m tinytuya scan`) terminaba en 18 s con
  `Scan Complete! Found 0 devices`, solo mostraba `New Broadcast from App at <IP-del-PC>`.
- La IP `192.168.1.152` que aparecía era el **propio PC** (el eco del broadcast),
  no el medidor.

**Causa**
- El scan usa **UDP broadcast de descubrimiento** (puertos 6666/6667/7000). El
  medidor EdgeAnt no responde a ese tipo de anuncio, o el broadcast no atraviesa
  el gateway.
- La comunicación **real** del script es **unicast** hacia `device_ip` — otro
  mecanismo completamente distinto.

**Solución**
- No depender del scan. Usar **unicast directo** con `device.status()`.
- Verificar la IP con la tabla ARP del PC (`arp -a`), no con el escáner.

> En PowerShell el `findstr` no encontró la MAC `D8:D6:68` porque las tablas ARP
> muestran las MAC con **guiones** (`d8-d6-68-77-91-56`), no con dos puntos.

---

## 2. SSH al gateway rechazado ("Connection refused")

**Síntoma**
- `ssh root@192.168.1.132` fallaba con `Connection refused` aunque se intentaba
  con `admin` y `root`.

**Causa**
- El servicio **Dropbear** (SSH) estaba configurado para escuchar **solo en la
  interfaz `ahwlan` (bridge br-ahwlan)** del HaLOW. El PC estaba en otra interfaz
  (`br-lan`, IP .132) → conexión rechazada por interfaz, no por contraseña.

**Solución**
- LuCI → **System → Administration → SSH Access** → en la instancia DropBear,
  cambiar **Interface** de `ahwlan:Bridge: "br-ahwlan"` a **"unspecified"**
  (escuchar en todas las interfaces), **Save & Apply**, y si no toma, reiniciar el
  router (System → Reboot).

---

## 3. El EdgeAnt "conectado" al AP pero sin IP (no aparecía en DHCP Leases)

**Síntoma**
- En LuCI → Status → Wireless → Clients el medidor aparecía asociado al AP
  (solo con su MAC, sin IP).
- `tinytuya.scan()` no lo encontraba y el script fallaba.

**Causa**
- El dispositivo estaba asociado a nivel WiFi pero **no completaba DHCP**, o quedó
  en **modo de emparejamiento** (configuración con SSID/contraseña de la red
  anterior). Un cliente sin IP no puede responder ninguna petición.

**Solución / verificación**
- Hacer un **ping sweep** y revisar la tabla ARP para ver si tiene IP aun sin
  lease visible en LuCI.
- **Reemparejar** el medidor con la app Smart Life/Tuya usando el SSID y
  contraseña **de la red del Alfa** (no la anterior).
- Dejar una **reserva DHCP** (Static Lease) para que la IP no cambie: LuCI →
  Network → DHCP and DNS → Static Leases → MAC `D8:D6:68:77:91:56` → IP
  `192.168.1.150`.

---

## 4. Diferentes `local_key` entre scripts → fallo silencioso

**Síntoma**
- Un script de prueba funcionaba (leía `dps`), pero el monitor "oficial" no
  entregaba datos.

**Causa**
- Cada script tenía **credenciales distintas**: el que funcionaba usaba
  `local_key = ']!pH]*v&G<tGis&H'` y `device_id = 'ebb5c0df93bc34b2c17asq'`;
  el otro tenía `local_key = "$o##oQDV7w>I8tyE"` (key vieja/incorrecta).

**Solución**
- Unificar las credenciales en un solo lugar (`config.json` / variables de
  entorno), verificar contra el `wizard` de tinytuya.

---

## 5. Cómo NUNCA dejar de operar por NAT (concepto crítico)

**Concepto**: NAT reescribe IPs y **bloquea conexiones entrantes** no solicitadas.
Como **el server inicia** la conexión hacia el EdgeAnt, el camino
`server → HaLOW → gateway → WiFi → EdgeAnt` debe ser **sin NAT** en el medio.

**Lo que se revisó en el gateway**
- `uci show network` / `uci show firewall` para confirmar que la interfaz del
  HaLOW **no esté** en zona `wan` con `masquerade`.
- Si la interfaz HaLOW quedó como WAN (NAT), la solución es:
  - LuCI → Network → Interfaces: agregar el HaLOW al **bridge `lan`** (mismo
    segmento) → así el unicast llega directo.
  - o, si se requiere subred separada: zona de firewall tipo `lan` (sin masq) +
    **rutas estáticas** entre subredes.
- Último recurso si el NAT es obligatorio: **Port Forwarding** UDP del puerto
  Tuya hacia el medidor y apuntar el script a la IP pública del gateway.

---

## 6. Aislamiento de clientes (AP Isolation)

**Síntoma potencial**: clientes WiFi del mismo AP no pueden hablarse entre sí
(rompería unicast y scan).

**Verificación**
- LuCI → Network → Wireless → Edit (del AP) → Advanced Settings →
  **"Isolate Clients"** debe estar **desmarcado**.
- No siempre aparece en la UI según la versión de LuCI; por eso la prueba
  definitiva es conectar el PC **por cable Ethernet** a un puerto LAN del gateway:
  si por cable funciona y por WiFi no → hay aislamiento forzado por driver.

---

## Resumen de lecciones

1. **No uses el scan para operar** — usa unicast con IP fija.
2. **La IP se verifica con ARP**, no con el escáner de Tinytuya.
3. **SSH/Dropbear puede estar atado a una interfaz** — revisar "unspecified".
4. **"Asociado ≠ con IP"** — si no hay DHCP, reempareja con el SSID correcto.
5. **Reserva DHCP** para que la IP nunca cambie.
6. **Una sola fuente de credenciales** — `config.json` gitignored.
7. **Sin NAT en el camino server→dispositivo** — el server inicia, el NAT lo bloquea.