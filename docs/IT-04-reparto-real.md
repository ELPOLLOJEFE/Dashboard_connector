# IT-04 — De "ver" a "repartir de verdad"

Esta IT es el paso siguiente, **cuando el panel ya tenga equipos y sepas cuáles
aguantan**. No la hagas antes: primero mide unos días.

## El punto de enganche: el fichero de modo

El agente escribe el modo actual en un fichero, siempre:

- Linux: `/var/lib/dashboard-connector/mode`
- Windows: `C:\ProgramData\dashboard-connector\mode`

Contiene una sola palabra: `off`, `receive_only`, `send_only` o `full`. Cualquier
cosa que reparta trabajo puede leerlo y respetarlo. Ese es el contrato, y es
deliberadamente tonto: un fichero de texto no se rompe con las versiones.

Además, si rellenas `DC_WORKER_UNIT` en la configuración del agente con el nombre
de un servicio local, el agente lo **arranca** cuando el modo es `receive_only` o
`full`, y lo **para** en `off` o `send_only`. Eso es todo lo que hace el agente:
no ejecuta nada que venga del hub.

---

## Camino A — Docker Swarm (solo equipos Linux)

El más directo si lo que quieres repartir son contenedores.

```bash
# En el equipo que coordina:
docker swarm init --advertise-addr IP-DEL-COORDINADOR
# Guarda el token que imprime.

# En cada equipo que vaya a ejecutar:
docker swarm join --token TOKEN-QUE-IMPRIMIO IP-DEL-COORDINADOR:2377
```

Puertos que hay que dejar pasar **entre los nodos, y solo entre ellos**:

| Puerto | Para qué |
|---|---|
| 2377/tcp | gestión del clúster |
| 7946/tcp + 7946/udp | descubrimiento entre nodos |
| 4789/udp | red interna de contenedores |

Etiqueta los nodos para que el trabajo caiga donde debe:

```bash
docker node update --label-add tipo=gpu       nombre-del-nodo
docker node update --label-add tipo=oficina   otro-nodo
docker node ls
```

Y en el servicio, la restricción:

```yaml
deploy:
  placement:
    constraints: [node.labels.tipo == gpu]
```

### Cómo se corresponde con los modos del panel

Swarm tiene su propio interruptor por nodo, y encaja casi uno a uno:

| Modo del panel | Equivalente en Swarm |
|---|---|
| Fuera | `docker node update --availability drain NODO` |
| Solo recibe | nodo *worker* con `--availability active` |
| Solo envía | nodo *manager* con `--availability drain` |
| Envía y recibe | nodo *manager* con `--availability active` |

```bash
# Esto se ejecuta SIEMPRE desde un manager, no desde el nodo afectado:
docker node update --availability drain NODO     # saca trabajo del nodo
docker node update --availability pause NODO     # no acepta nada nuevo
docker node update --availability active NODO    # vuelve al pool
```

**Importante:** el panel no ejecuta estos comandos por ti, a propósito (sería dar
al hub poder de ejecución sobre todos los nodos). El panel es la decisión y el
registro; el comando lo lanzas tú desde el manager. Si más adelante quieres
automatizarlo, el sitio correcto es un script *en el manager* que lea la API del
hub (`GET /api/v1/nodes`) y aplique las disponibilidades — el token de admin se
queda en una sola máquina y los agentes siguen sin poder ejecutar nada.

Para la parte visual de Swarm, **Portainer CE** da la lista de nodos y el cambio
de disponibilidad con un clic.

---

## Camino B — Cola de trabajos (sirve también para Windows)

Si lo que quieres repartir son *trabajos* (transcripciones, lotes de imágenes,
informes) y no servicios permanentes, esto es más simple y más robusto que Swarm,
y funciona en PCs de oficina que se apagan.

Montaje mínimo:

1. Un **Redis** en el servidor del hub.
2. En cada equipo, un **worker** (un script) que coge trabajos de la cola.
3. El worker arranca comprobando el fichero de modo: si no es `receive_only` ni
   `full`, no coge nada y espera.
4. Instala ese worker como servicio y pon su nombre en `DC_WORKER_UNIT`: el
   agente lo arrancará y lo parará solo, siguiendo el panel.

Esquema del worker, lo esencial:

```python
MODE_FILE = r"C:\ProgramData\dashboard-connector\mode"  # o /var/lib/... en Linux

def comparte():
    try:
        with open(MODE_FILE) as f:
            return f.read().strip() in ("receive_only", "full")
    except FileNotFoundError:
        return False

while True:
    if not comparte():
        time.sleep(30)
        continue
    trabajo = cola.coger(timeout=30)   # Redis BLPOP, Celery, RQ...
    if trabajo:
        procesar(trabajo)              # y re-encolar si falla
```

Dos reglas que no te puedes saltar en PCs de oficina:

- **Trabajos reintentables.** El PC se puede apagar a media tarea. Si un trabajo
  perdido a medias deja datos corruptos, ese trabajo no va a un PC de oficina.
- **Prioridad baja.** Lanza el proceso con prioridad reducida (`nice -n 19` en
  Linux, `Start-Process -Priority BelowNormal` en Windows) para que quien esté
  usando el PC no note nada.

---

## Cuál elegir

| Tu caso | Camino |
|---|---|
| Servidores Linux, quiero mover contenedores | A — Swarm |
| Mezcla de Windows y Linux, trabajos por lotes | B — cola |
| Solo quiero saber qué hay y decidir a mano | ninguno: el panel ya te vale |

No hace falta elegir para siempre: los dos leen el mismo fichero de modo y
conviven sin problema.
