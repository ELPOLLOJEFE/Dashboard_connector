# IT-00 — Qué es esto y cómo encaja

## Objetivo

Tener un panel que diga, en cualquier momento, **qué equipos de la red están
compartiendo CPU y RAM**, cuánto ofrecen, y poder **cambiarles el modo** desde una
sola pantalla.

## Lo que esto es y lo que no es

**Es:** un registro central (el *hub*) + un agente diminuto en cada equipo. El
agente dice "soy este equipo, tengo tantos núcleos y tanta RAM, estoy en este
modo". El panel lo muestra y te deja cambiar el modo.

**No es:** un repartidor de trabajo. Esto es la capa de *inventario y control*.
Cuando quieras que el trabajo se mueva de verdad a esos equipos, se conecta
encima (Docker Swarm o una cola de trabajos) — eso está en la `IT-04`.

**Y sobre todo: no fusiona la RAM.** No existe forma práctica de que un equipo
use la RAM de otro por red. Lo que se consigue es *colocar cada trabajo donde
hay hueco*, con la decisión tomada a la vista de este panel.

## Los cuatro modos

| Modo | Qué significa | Para qué sirve |
|---|---|---|
| **Fuera** (`off`) | No comparte nada. Solo informa de su estado. | Por defecto. Equipo recién instalado, o retirado del pool. |
| **Solo recibe** (`receive_only`) | Ejecuta trabajo que le manden, pero no reparte. | Lo normal en un PC o servidor que presta capacidad. |
| **Solo envía** (`send_only`) | Reparte trabajo, no ejecuta nada. | El coordinador, para que no se ahogue él mismo. |
| **Envía y recibe** (`full`) | Las dos cosas. | Un servidor potente que además coordina. |

Todo equipo entra en `off`. Nada empieza a compartir sin que tú lo cambies en el
panel.

## Arquitectura

```
   PC Windows ──┐
   PC Windows ──┤   latido HTTP cada 20 s        ┌──────────────┐
   Servidor   ──┼──────────────────────────────> │     HUB      │ <── tú, en el
   Servidor   ──┤   (CPU, RAM, disco, modo)      │  panel web   │     navegador
   Portátil   ──┘   <────── modo deseado ─────── └──────────────┘
```

- El agente **sale** hacia el hub. No abre ningún puerto de escucha.
- El hub **nunca** manda comandos al agente: solo publica un modo de los cuatro.
  Es el agente, en local, quien decide qué hacer con él. Esto es a propósito: un
  agente en 200 equipos que acepte comandos remotos es una puerta trasera.
- Un único puerto en juego: el del hub (8700 por defecto).

## Orden de instalación

1. `IT-01` — montar el hub (una sola vez, en el servidor).
2. `IT-02` — agente en cada equipo Linux.
3. `IT-03` — agente en cada equipo Windows.
4. `IT-04` — cuando el panel ya esté poblado, conectar el reparto real.

## Antes de empezar: dos decisiones

**¿Qué equipos van a compartir de verdad?** Un PC de oficina que se apaga a las
18:00 no sirve para servicios permanentes; sí para trabajos por lotes que se
puedan reintentar. Instala el agente en todo lo que quieras *medir* — pero pon en
modo compartir solo lo que de verdad aguante.

**¿Compensa?** Si el objetivo es que un servidor concreto no se ahogue, ampliarle
la RAM suele salir más barato y más rápido que montar y mantener un clúster. Este
panel te da los números para decidirlo con datos en vez de por intuición.
