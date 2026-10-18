# IT-03 — Instalar el agente en un equipo Windows

## Objetivo
Que el PC o servidor Windows aparezca en el panel. Entra en modo **Fuera**.

## Requisitos
- Windows 10 / 11 / Server 2016 o posterior.
- Permisos de **administrador local**.
- Llegar al hub por red.

## Antes de empezar, ten a mano
- `HUB` = `http://IP-DEL-HUB:8700`
- `TOKEN` = el **token de agente** de la IT-01

---

## Paso 1 — Python (si no está)

PowerShell **como administrador**:

```powershell
python --version
# Si da error:
winget install -e --id Python.Python.3.12
# Cierra y vuelve a abrir PowerShell para que coja el PATH.
```

## Paso 2 — Instalar el agente

Cambia las dos primeras líneas y pega el bloque completo:

```powershell
$HUB   = "http://IP-DEL-HUB:8700"
$TOKEN = "pega-aqui-el-token-de-agente"

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$tmp = "$env:TEMP\dc"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Invoke-WebRequest -Uri "https://github.com/ELPOLLOJEFE/Dashboard_connector/archive/refs/heads/main.zip" `
  -OutFile "$env:TEMP\dc.zip"
Expand-Archive "$env:TEMP\dc.zip" -DestinationPath $tmp -Force
cd "$tmp\Dashboard_connector-main\agent"
.\install_agent.ps1 -HubUrl $HUB -Token $TOKEN -ShareCpuPct 25 -ShareRamMb 1024
```

En un PC de oficina deja `-ShareCpuPct 25 -ShareRamMb 1024`: que la persona que
lo usa no note nada. En un servidor Windows sube a `70` y `8192`.

### Si el equipo no sale a internet
Copia la carpeta `agent\` a mano (pendrive o recurso compartido) y ejecuta solo
la última línea desde donde la hayas dejado.

---

## Verificación

```powershell
Get-ScheduledTask -TaskName DashboardConnectorAgent | Select State
Get-Content "C:\ProgramData\dashboard-connector\agent.log" -Tail 20
```

`State` debe ser `Running` y en el log la línea `agente 1.0.0 | equipo=...`.
En el panel aparece el equipo con su CPU y RAM.

## Qué hacer si no aparece

| Síntoma | Causa | Arreglo |
|---|---|---|
| log vacío o no existe | la tarea no arrancó | `Start-ScheduledTask -TaskName DashboardConnectorAgent` |
| `hub respondio 401` | token mal copiado | relanza `install_agent.ps1` con el token correcto |
| `sin contacto con el hub` | red o cortafuegos | `Test-NetConnection IP-DEL-HUB -Port 8700` |
| CPU como `s/d` | falta `psutil` | `python -m pip install psutil` y reinicia la tarea |

## Nota importante sobre PCs de oficina
La tarea arranca **al encender el equipo**, con la cuenta SYSTEM. Si el usuario
apaga el PC, el equipo sale del panel como *Caído* — es correcto, no es un fallo.
Por eso un PC de oficina solo sirve para trabajos por lotes reintentables, nunca
para un servicio que deba estar siempre en pie.

## Vuelta atrás
```powershell
Unregister-ScheduledTask -TaskName DashboardConnectorAgent -Confirm:$false
Remove-Item -Recurse -Force "C:\Program Files\dashboard-connector", "C:\ProgramData\dashboard-connector"
```
Y bórralo del panel.

## Qué deja instalado, exactamente
| Ruta | Qué es |
|---|---|
| `C:\Program Files\dashboard-connector\dc_agent.py` | el agente |
| `C:\Program Files\dashboard-connector\run_agent.cmd` | arrancador con la config y el token (ACL: solo SYSTEM y administradores) |
| `C:\ProgramData\dashboard-connector\mode` | modo actual |
| `C:\ProgramData\dashboard-connector\agent.log` | log |
| Tarea programada `DashboardConnectorAgent` | el servicio |

El log se va añadiendo sin límite. Crece muy despacio (unas líneas por cambio de
modo), pero si quieres cortarlo de raíz, una tarea mensual:

```powershell
Clear-Content "C:\ProgramData\dashboard-connector\agent.log"
```
