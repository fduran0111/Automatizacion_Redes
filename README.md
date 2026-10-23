# Automatización FortiGate

Herramienta en Python que lee un Excel de **solicitudes de permisos de firewall**, las valida y las convierte en **objetos de dirección** y **políticas** en un FortiGate a través de su API REST.

Además genera un **Excel de revisión** que marca, fila por fila, qué hay que corregir antes de crear las reglas.

---

## Qué hace

1. **Lee el Excel** de solicitudes (`permisos.xlsx`, hoja `CONFIGURADO`).
2. **Valida cada fila**:
   - IPs y redes de origen y destino.
   - Puertos y servicios, traducidos a servicios que existen en el Forti.
   - **Política de seguridad**: bloquea o advierte según si el tráfico va a la LAN o a internet.
3. **Compara** las IPs con los objetos de dirección del Forti y crea los que falten.
4. **Arma las reglas** (agrupando filas con el mismo destino y servicios) y las muestra en un *dry-run*.
5. **Crea las políticas** en el Forti, **deshabilitadas**, para revisarlas antes de activarlas.
6. **Genera un Excel de revisión** con el estado de cada fila y la celda del problema marcada.

> Las opciones que modifican el Forti (crear objetos y crear políticas) **siempre piden confirmación**.

---

## Requisitos

- **Python 3.13 o superior** (la clasificación LAN/INTERNET depende de cómo Python reconoce las redes públicas).
- Librerías:

```
py -m pip install openpyxl requests python-dotenv
```

- Acceso al FortiGate (red de la oficina o VPN) y un **token de API**.

---

## Configuración

Crea un archivo **`.env`** en la carpeta del proyecto:

```
FORTI_HOST=192.168.1.99
FORTI_KEY=tu_token_de_api
FORTI_VDOM=root

# Opcionales: interfaces de las políticas (por defecto port1 -> port2)
FORTI_SRCINTF=port1
FORTI_DSTINTF=port2
```

> ⚠️ El `.env` contiene el token del Forti: **no lo compartas ni lo subas a un repositorio**.

---

## Archivos del proyecto

| Archivo | Para qué sirve |
|---|---|
| `menu.py` | **Punto de entrada.** Menú con todas las opciones. |
| `validacion.py` | Lee el Excel y valida cada fila (IPs, servicios y seguridad). |
| `servicios.py` | Descarga los servicios del Forti a `puerto.json` y los traduce (`443` → `HTTPS`). |
| `seguridad.py` | Decide si un servicio está permitido según vaya a la LAN o a internet. |
| `revision_excel.py` | Genera el Excel de revisión con colores y comentarios. |
| `reglasForti.py` | Objetos de dirección, agrupación de solicitudes, reglas y consulta de políticas. |
| `forti_api.py` | Única parte que habla con la API del FortiGate. |
| `puerto.json` | Catálogo de servicios del Forti (se genera con la opción 1). |
| `puerto_seguridad.json` | Política de seguridad: qué servicios se permiten, advierten o bloquean. |
| `permisos.xlsx` | Excel de solicitudes de entrada. |
| `.env` | Datos de conexión al Forti (no se comparte). |

---

## Uso

Desde la carpeta del proyecto:

```
py menu.py
```

| Opción | Qué hace | ¿Modifica el Forti? |
|---|---|---|
| **1** | Sincroniza los servicios del Forti a `puerto.json` | No |
| **2** | Lee y valida el Excel, y muestra el resultado | No |
| **3** | Compara las IPs del Excel con los objetos del Forti | No |
| **4** | Crea los objetos de dirección que faltan | **Sí** (pide confirmación) |
| **5** | Arma las reglas y las muestra (*dry-run*) | No |
| **6** | Muestra las políticas que ya existen en el Forti | No |
| **7** | Crea las políticas en el Forti | **Sí** (pide confirmación) |
| **8** | Genera el Excel de revisión | No |
| **0** | Salir | — |

**Flujo recomendado:** `1` (la primera vez) → `8` (revisar y corregir el Excel) → `3` → `4` → `5` → `7` → `6` (verificar).

Las opciones se encadenan solas: si eliges la 5 sin haber pasado por la 3, el programa la ejecuta antes.

---

## Formato del Excel de entrada

Hoja **`CONFIGURADO`**, datos desde la **fila 4**:

| Columna | Contenido | Ejemplos válidos |
|---|---|---|
| **E** | IP / red de origen | `10.1.1.1` · `10.1.1.0/24` · varias separadas por espacio, coma o salto de línea |
| **F** | IP / red de destino | igual que el origen |
| **G** | Puertos o servicios | `443` · `443, 80` · `514/udp` · `udp/514` · `RDP` · `Web Access` |

Las filas con E, F y G vacías se ignoran.

**Queda en REVISAR (no se crea la regla):**
- Celda de origen o destino vacía.
- Texto que no es IP (por ejemplo `host`, `VLAN 20`, un nombre de objeto).
- **Rangos** escritos con guion (`10.0.0.1-10.0.0.20`): se marcan para que alguien los confirme.
- Puertos sin servicio en el Forti (se listan al final para pedir que los creen).
- Servicios no permitidos por la política de seguridad.

---

## Política de seguridad (`puerto_seguridad.json`)

Cada solicitud se clasifica según hacia dónde va el tráfico:

- **LAN**: origen y destino en redes privadas.
- **Hacia internet**: algún destino es una IP pública.
- **Desde internet**: algún origen es una IP pública.

Los servicios se agrupan en **categorías** (transferencia de archivos, administración remota, bases de datos, etc.), y cada categoría define una acción por sentido:

| Acción | Resultado |
|---|---|
| `permitir` | Pasa sin aviso. |
| `advertir` | Pasa, pero con **WARNING** para que alguien lo revise. |
| `bloquear` | La fila queda en **REVISAR** y no se crea la regla. |

Ejemplo: FTP está permitido en la LAN, pero bloqueado hacia o desde internet.

La política se puede ajustar **editando el JSON**, sin tocar el código.

---

## Excel de revisión (opción 8)

Genera una **copia** del Excel (el original **no se modifica**) con el nombre `permisos_DD_MM.xlsx`, que incluye:

- Columna **ESTADOS**: 🟥 `REVISAR` · 🟨 `WARNING` · 🟩 `OK`.
- Columna **REVISION**: los errores y warnings de cada fila.
- La **celda con el problema** (origen, destino o puertos) pintada de rojo o amarillo, con un **comentario** que explica el motivo al pasar el mouse.

---

## Problemas frecuentes

| Error | Causa | Solución |
|---|---|---|
| `PermissionError: [Errno 13] Permission denied` | El Excel está abierto o OneDrive lo está sincronizando | Cerrar el archivo en Excel y volver a intentar |
| `puerto.json no tiene un formato válido` | `puerto.json` está vacío o dañado | Ejecutar la opción **1** |
| `No existe puerto_seguridad.json` | Falta el archivo de política o tiene otro nombre | Revisar que exista `puerto_seguridad.json` en la carpeta |
| `Falta FORTI_HOST / FORTI_KEY en el archivo .env` | No hay `.env` o le faltan datos | Crear o completar el `.env` |
| Errores de conexión o *timeout* | Sin acceso al Forti | Revisar la VPN o la red y el `FORTI_HOST` |
| `Falta el servicio en el Forti para el puerto X` | No existe un servicio con exactamente ese puerto | Pedir que lo creen, o escribir el nombre del servicio en el Excel |

---

## Notas importantes

- Pensado para **laboratorio**: la verificación del certificado SSL está desactivada (`VERIFY_SSL = False` en `forti_api.py`).
- Las políticas se crean **deshabilitadas** y quedan **al final** de la lista. Revisar que ninguna regla *deny* anterior las tape.
- Todas las reglas usan las interfaces del `.env` (`FORTI_SRCINTF` → `FORTI_DSTINTF`). Revisarlas antes de activar las políticas.
- Se recomienda trabajar fuera de OneDrive para evitar bloqueos al guardar archivos.

---

## Pendientes

- Detectar máscaras escritas aparte (`10.0.0.0 255.255.255.0`).
- Calcular las interfaces automáticamente según las rutas del Forti.
- Detectar políticas duplicadas por contenido, no solo por nombre.
- Clasificar como internet los objetos `all`, FQDN y geografía.
- Registro (CSV) de los objetos y políticas creados.
