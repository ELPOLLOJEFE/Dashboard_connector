# Dashboard Connector

Panel ligero para saber **qué equipos de una red están compartiendo CPU y RAM**, y
cambiarles el modo desde una sola pantalla.

Un *hub* central + un agente diminuto en cada equipo (Linux y Windows). Sin
dependencias en el agente más allá de Python, sin puertos de escucha en los
equipos, sin ejecución remota de comandos.

```
   PC Windows ──┐
   Servidor   ──┼── latido HTTP cada 20 s ──>  HUB  <── panel web
   Portátil   ──┘   <──── modo deseado ─────
```

## Los cuatro modos

| Modo | Significa |
|---|---|
| **Fuera** | no comparte nada, solo informa |
| **Solo recibe** | ejecuta trabajo que le manden, no reparte |
| **Solo envía** | reparte trabajo, no ejecuta |
| **Envía y recibe** | las dos cosas |

Todo equipo entra en **Fuera**. Nada comparte sin que lo cambies tú.

## Qué muestra el panel

- Equipos en línea / caídos, con cuánto hace que se les vio.
- CPU y RAM de cada uno, en uso y total.
- Cuánto **ofrece** cada equipo cuando comparte (núcleos y GB).
- Totales del pool: equipos compartiendo, núcleos y GB disponibles.
- GPU y versión de Docker detectadas, si las hay.
- Histórico de cambios de modo y altas de equipos.

## Instalación

Las instrucciones paso a paso, para copiar y pegar, están en `docs/`:

| | |
|---|---|
| [IT-00](docs/IT-00-resumen.md) | qué es, qué no es, los cuatro modos |
| [IT-01](docs/IT-01-hub.md) | montar el hub (una vez) |
| [IT-02](docs/IT-02-agente-linux.md) | agente en Linux |
| [IT-03](docs/IT-03-agente-windows.md) | agente en Windows |
| [IT-04](docs/IT-04-reparto-real.md) | conectar el reparto real (Swarm o cola de trabajos) |

Resumen del hub:

```bash
git clone https://github.com/ELPOLLOJEFE/Dashboard_connector.git
cd Dashboard_connector
cp .env.example .env
sed -i "s|^DC_AGENT_TOKEN=.*|DC_AGENT_TOKEN=$(openssl rand -hex 24)|" .env
sed -i "s|^DC_ADMIN_TOKEN=.*|DC_ADMIN_TOKEN=$(openssl rand -hex 24)|" .env
chmod 600 .env
docker compose up -d --build
```

Panel en `http://IP-DEL-SERVIDOR:8700`.

## Lo que esto NO hace

- **No fusiona la RAM de varias máquinas.** No existe forma práctica de hacerlo
  sobre Ethernet. Lo que se consigue es colocar cada trabajo donde hay hueco.
- **No reparte trabajo por sí mismo.** Es la capa de inventario y control; el
  reparto se engancha encima (ver IT-04).
- **No ejecuta comandos remotos.** El hub solo publica uno de cuatro modos; el
  agente decide en local qué hacer con él.

## Seguridad

- **Dos tokens separados.** El de agente va en todos los equipos y se considera
  comprometible: con él solo se puede mandar un latido. El de admin, que es el que
  cambia modos, se queda en tu navegador.
- El agente **sale** hacia el hub; no abre ningún puerto.
- El hub no manda comandos: el único dato que viaja hacia el equipo es una
  palabra de una lista cerrada de cuatro.
- Publica el hub detrás de un proxy inverso con HTTPS y limita el 8700 a las IPs
  de los equipos con agente. Sobre HTTP plano, el token de agente viaja en claro.

## API

| Método | Ruta | Token | Para qué |
|---|---|---|---|
| `POST` | `/api/v1/heartbeat` | agente | latido del equipo; devuelve el modo deseado |
| `GET` | `/api/v1/nodes` | admin | estado de todos los equipos + pool + eventos |
| `POST` | `/api/v1/nodes/{id}/mode` | admin | cambiar el modo |
| `POST` | `/api/v1/nodes/{id}/notes` | admin | nota libre en la ficha |
| `DELETE` | `/api/v1/nodes/{id}` | admin | olvidar un equipo |
| `GET` | `/healthz` | — | comprobación de vida |

## Licencia

**Apache License 2.0** — ver [LICENSE](LICENSE) y [NOTICE](NOTICE).
Copyright 2026 Alex Fernandes (ELPOLLOJEFE).

En resumen: puedes usarlo, modificarlo y redistribuirlo, incluso en productos
comerciales. A cambio tienes que conservar el aviso de copyright, incluir una
copia de la licencia e **indicar qué ficheros has modificado**. Incluye concesión
expresa de patentes. No da derecho a usar el nombre ni las marcas del autor para
promocionar derivados.
