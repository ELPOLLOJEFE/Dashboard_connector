# IT-02 — Instalar el agente en un equipo Linux

## Objetivo
Que este equipo aparezca en el panel. Entra en modo **Fuera**: todavía no
comparte nada.

## Requisitos
- `python3` instalado (viene en cualquier distro actual).
- Llegar al hub por red.
- `sudo` en el equipo.

## Antes de empezar, ten a mano
- `HUB` = `http://IP-DEL-HUB:8700`
- `TOKEN` = el **token de agente** de la IT-01 (no el de admin)

---

## Pegar esto en el equipo, de una vez

Cambia las dos primeras líneas y pega el bloque completo en la terminal:

```bash
HUB="http://IP-DEL-HUB:8700"
TOKEN="pega-aqui-el-token-de-agente"

sudo apt-get update -qq && sudo apt-get install -y -qq git python3 || \
  sudo dnf install -y git python3
git clone https://github.com/ELPOLLOJEFE/Dashboard_connector.git /tmp/dc
cd /tmp/dc/agent
chmod +x install_agent.sh
sudo DC_HUB_URL="$HUB" DC_AGENT_TOKEN="$TOKEN" \
     DC_SHARE_CPU_PCT=50 DC_SHARE_RAM_MB=2048 \
     ./install_agent.sh
```

Las dos variables de reparto dicen **cuánto está dispuesto a ceder este equipo**
cuando lo pongas a compartir: la mitad de sus núcleos y 2 GB en el ejemplo.
Ajústalas por equipo (un servidor grande puede ceder 80% y 8192; un PC de
oficina, 25% y 1024).

### Si no hay git o el equipo no sale a internet

Copia solo los dos ficheros desde tu puesto:

```bash
scp agent/dc_agent.py agent/install_agent.sh usuario@IP-DEL-EQUIPO:/tmp/
# y en el equipo:
cd /tmp && chmod +x install_agent.sh
sudo DC_HUB_URL="http://IP-DEL-HUB:8700" DC_AGENT_TOKEN="xxxx" ./install_agent.sh
```

---

## Verificación

```bash
systemctl status dashboard-connector-agent --no-pager
journalctl -u dashboard-connector-agent -n 20 --no-pager
```

Debes ver la línea `agente 1.0.0 | equipo=... | hub=...` y **ningún** error de
contacto. En el panel aparece el equipo con sus núcleos y su RAM, en modo
**Fuera**.

## Qué hacer si no aparece

| Síntoma en el log | Causa | Arreglo |
|---|---|---|
| `hub respondio 401` | token de agente mal copiado | corrige `/etc/dashboard-connector.env` y `systemctl restart dashboard-connector-agent` |
| `sin contacto con el hub` | red o cortafuegos | `curl -v http://IP-DEL-HUB:8700/healthz` desde el equipo |
| CPU aparece como `s/d` | sin `psutil` y lectura fallida | `sudo apt-get install -y python3-psutil && systemctl restart dashboard-connector-agent` |

## Ponerlo a compartir
En el panel, columna **Cambiar a** → *Solo recibe*. En un latido o dos la columna
**Modo** pasa a *Solo recibe* y el equipo empieza a sumar en los contadores de
arriba.

## Vuelta atrás
```bash
cd /tmp/dc/agent && sudo ./uninstall_agent.sh
```
Y bórralo del panel (el botón de la fila) para que no quede como caído.

## Qué deja instalado, exactamente
| Ruta | Qué es |
|---|---|
| `/opt/dashboard-connector/dc_agent.py` | el agente |
| `/etc/dashboard-connector.env` | configuración y token (modo 600, solo root) |
| `/etc/systemd/system/dashboard-connector-agent.service` | el servicio |
| `/var/lib/dashboard-connector/mode` | modo actual, en texto plano |

Nada más. No toca cortafuegos, ni usuarios, ni paquetes del sistema.
