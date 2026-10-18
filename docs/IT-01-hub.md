# IT-01 — Montar el hub (una sola vez)

## Objetivo
Dejar el panel funcionando en el servidor, con sus dos tokens.

## Requisitos
- Un servidor Linux encendido siempre, con Docker y `docker compose`.
- Puerto `8700` libre.
- Que el resto de equipos lleguen a ese servidor por red.

---

## Paso 1 — Traer el proyecto

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/ELPOLLOJEFE/Dashboard_connector.git
cd Dashboard_connector
```

## Paso 2 — Generar los dos tokens

Son distintos a propósito: el de **agente** acaba en todos los equipos (y por
tanto se considera comprometible); el de **admin** solo lo tienes tú y es el que
permite cambiar modos.

```bash
cp .env.example .env
sed -i "s|^DC_AGENT_TOKEN=.*|DC_AGENT_TOKEN=$(openssl rand -hex 24)|" .env
sed -i "s|^DC_ADMIN_TOKEN=.*|DC_ADMIN_TOKEN=$(openssl rand -hex 24)|" .env
chmod 600 .env
cat .env
```

**Copia los dos valores a tu gestor de contraseñas ahora.** El de agente lo vas a
necesitar en cada equipo; el de admin, para entrar al panel.

## Paso 3 — Arrancar

```bash
docker compose up -d --build
docker compose ps
```

## Paso 4 — Verificar

```bash
curl -s localhost:8700/healthz
# -> {"ok":true}

# Sin token debe rechazar:
curl -s -o /dev/null -w '%{http_code}\n' localhost:8700/api/v1/nodes
# -> 401

# Con el token de admin debe contestar el pool vacío:
source .env
curl -s -H "Authorization: Bearer $DC_ADMIN_TOKEN" localhost:8700/api/v1/nodes
# -> {"pool":{"nodes_total":0,...},"nodes":[],"events":[]}
```

Abre `http://IP-DEL-SERVIDOR:8700` en el navegador. Te pedirá el token de admin
una vez y lo guardará en el navegador. Verás el panel vacío: normal, todavía no
hay agentes.

## Paso 5 — Cerrar el puerto a quien no toca

El hub no debería estar abierto a toda la red. Deja entrar solo a los equipos que
vayan a llevar agente, y a tu puesto:

```bash
# Ejemplo con ufw: pon TU red o, mejor, las IPs concretas de los equipos
sudo ufw allow from TU.RED.0.0/24 to any port 8700 proto tcp
sudo ufw deny 8700/tcp
```

Si tienes un proxy inverso con HTTPS, mejor: pon `DC_BIND=127.0.0.1` en el `.env`,
reinicia, y publica el panel por el proxy con un nombre de dominio. El agente
acepta `https://` sin tocar nada.

---

## Verificación final
- [ ] `/healthz` responde `{"ok":true}`
- [ ] sin token da 401
- [ ] el panel carga en el navegador
- [ ] los dos tokens están guardados en el gestor de contraseñas
- [ ] el puerto 8700 no está abierto a toda la red

## Vuelta atrás
```bash
docker compose down          # para el hub, conserva los datos
docker compose down -v       # borra también el histórico de equipos
```

## Operación diaria
```bash
docker compose logs -f hub   # ver qué llega
docker compose pull && docker compose up -d --build   # actualizar
```
Copia de seguridad: el único dato es el volumen `hub-data` (`/data/hub.db`).
