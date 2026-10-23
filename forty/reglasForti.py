import ipaddress
import json
import os
 
import forti_api
 
# Configurables desde el .env (por defecto, los de laboratorio)
INTERFAZ_ORIGEN = os.getenv("FORTI_SRCINTF", "port1")
INTERFAZ_DESTINO = os.getenv("FORTI_DSTINTF", "port2")
 
# Las políticas se crean DESHABILITADAS para revisarlas antes de activarlas
ESTADO_POLITICA = "disable"
 
# El FortiGate limita el nombre de una política a 35 caracteres
MAX_NOMBRE_POLITICA = 35
 
ERRORES_API = forti_api.ERRORES
 
 
# --------------------------------------------------
# 1. OBJETOS DE DIRECCIÓN
# --------------------------------------------------
 
def construir_objeto(direccion):
 
    try:
        red = ipaddress.ip_network(direccion, strict=False)
    except ValueError:
        return None, f"Dirección inválida: {direccion}"
 
    if red.version != 4:
        return None, f"IPv6 no soportada: {direccion}"
 
    if red.prefixlen == 32:
        nombre = "HOST_" + str(red.network_address).replace(".", "_")
    else:
        nombre = (
            "NET_"
            + str(red.network_address).replace(".", "_")
            + f"_{red.prefixlen}"
        )
 
    objeto = {
        "name": nombre,
        "type": "ipmask",
        "subnet": f"{red.network_address} {red.netmask}",
        "comment": "Creado mediante automatización",
    }
 
    return objeto, None
 
 
def dry_run_objetos(unicas):
 
    print("\n--- DRY RUN OBJETOS ---")
 
    for direccion in unicas:
 
        objeto, error = construir_objeto(direccion)
 
        if error:
            print(f"[ERROR] {error}")
        else:
            print(f"  {objeto['name']} -> {objeto['subnet']}")
 
 
def normalizar_subnet(subnet):
 
    try:
        if isinstance(subnet, list):
            subnet = " ".join(str(valor) for valor in subnet)
 
        partes = str(subnet).split()
 
        if len(partes) == 2:
            red = ipaddress.ip_network(f"{partes[0]}/{partes[1]}", strict=False)
        elif len(partes) == 1:
            red = ipaddress.ip_network(partes[0], strict=False)
        else:
            return None
 
        return red if red.version == 4 else None
 
    except ValueError:
        return None
 
 
def mapear_objetos_por_ip(objetos):
    """Devuelve {'10.0.0.1/32': 'nombre_del_objeto'} con los objetos del Forti."""
 
    mapa = {}
 
    for objeto in objetos:
 
        nombre = objeto.get("name")
        red = normalizar_subnet(objeto.get("subnet", ""))
 
        if nombre and red is not None:
            mapa.setdefault(str(red), nombre)
 
    return mapa
 
 
def comparar_direcciones(unicas, objetos):
    """Compara las IPs del Excel con los objetos del Forti. Devuelve las que faltan."""
 
    print("\n--- COMPARACIÓN CON EL FORTI ---")
 
    mapa = mapear_objetos_por_ip(objetos)
    faltantes = []
 
    for direccion in unicas:
 
        try:
            red = ipaddress.ip_network(direccion, strict=False)
        except ValueError:
            print(f"  {direccion} -> DIRECCIÓN INVÁLIDA")
            continue
 
        if red.version != 4:
            print(f"  {direccion} -> IPv6 NO SOPORTADA")
            continue
 
        if str(red) in mapa:
            print(f"  {direccion} -> YA EXISTE (objeto: {mapa[str(red)]})")
        else:
            print(f"  {direccion} -> FALTA")
            faltantes.append(str(red))
 
    print(f"\n[INFO] Objetos en el Forti: {len(mapa)}")
    print(f"[INFO] Objetos por crear: {len(faltantes)}")
 
    return faltantes
 
 
def crear_objetos_faltantes(faltantes):
 
    if not faltantes:
        print("\n[OK] No hay objetos que crear.")
        return
 
    print("\n--- OBJETOS PENDIENTES DE CREACIÓN ---")
 
    objetos = []
 
    for direccion in faltantes:
 
        objeto, error = construir_objeto(direccion)
 
        if error:
            print(f"[ERROR] {error}")
            continue
 
        objetos.append(objeto)
        print(f"  {objeto['name']} -> {objeto['subnet']}")
 
    if not objetos:
        print("[INFO] No hay objetos válidos para crear.")
        return
 
    confirmacion = input(
        f"\n¿Crear estos {len(objetos)} objetos en el FortiGate? (si/no): "
    ).strip().lower()
 
    if confirmacion != "si":
        print("[INFO] Creación cancelada.")
        return
 
    for objeto in objetos:
 
        try:
            forti_api.crear_direccion(objeto)
            print(f"[OK] Objeto creado: {objeto['name']}")
 
        except ERRORES_API as error:
            print(f"[ERROR] No se pudo crear {objeto['name']}: {error}")
 
 
# --------------------------------------------------
# 2. AGRUPAR SOLICITUDES
# --------------------------------------------------
 
def agrupar_solicitudes(solicitudes):
    """Une filas con el mismo destino y los mismos servicios (suma los orígenes)."""
 
    grupos = {}
 
    for solicitud in solicitudes:
 
        if solicitud["estado"] != "VALIDADA":
            continue
 
        clave = (
            tuple(sorted(solicitud["destinos"])),
            tuple(sorted(solicitud["servicios"])),
        )
 
        if clave not in grupos:
            grupos[clave] = {
                "filas": [],
                "origenes": [],
                "destinos": solicitud["destinos"],
                "servicios": solicitud["servicios"],
                "advertencias": [],
            }
 
        grupo = grupos[clave]
        grupo["filas"].append(str(solicitud["fila_excel"]))
 
        for origen in solicitud["origenes"]:
            if origen not in grupo["origenes"]:
                grupo["origenes"].append(origen)

        for advertencia in solicitud.get("advertencias", []):
            if advertencia not in grupo["advertencias"]:
                grupo["advertencias"].append(advertencia)
 
    return [
        {
            "fila_excel": "-".join(grupo["filas"]),
            "origenes": grupo["origenes"],
            "destinos": grupo["destinos"],
            "servicios": grupo["servicios"],
            "estado": "VALIDADA",
            "errores": [],
            "advertencias": grupo["advertencias"],
        }
        for grupo in grupos.values()
    ]
 
 
# --------------------------------------------------
# 3. REGLAS
# --------------------------------------------------
 
def _nombres_de_objetos(direcciones, mapa_objetos, tipo):
 
    nombres = []
 
    for direccion in direcciones:
 
        red = str(ipaddress.ip_network(direccion, strict=False))
        nombre = mapa_objetos.get(red)
 
        if nombre is None:
            raise ValueError(f"No existe objeto para el {tipo}: {direccion}")
 
        nombres.append({"name": nombre})
 
    return nombres
 
 
def construir_regla(solicitud, mapa_objetos):
 
    return {
        "name": f"FILA-{solicitud['fila_excel']}"[:MAX_NOMBRE_POLITICA],
        "srcintf": [{"name": INTERFAZ_ORIGEN}],
        "dstintf": [{"name": INTERFAZ_DESTINO}],
        "srcaddr": _nombres_de_objetos(
            solicitud["origenes"], mapa_objetos, "origen"
        ),
        "dstaddr": _nombres_de_objetos(
            solicitud["destinos"], mapa_objetos, "destino"
        ),
        "service": [{"name": nombre} for nombre in solicitud["servicios"]],
        "action": "accept",
        "schedule": "always",
        "nat": "disable",
        "status": ESTADO_POLITICA,
    }
 
 
def construir_reglas(solicitudes, mapa_objetos):
    """Construye todas las reglas posibles. Las que fallan se informan y se omiten."""
 
    reglas = []
 
    for solicitud in solicitudes:
 
        if solicitud["estado"] != "VALIDADA":
            continue
 
        try:
            reglas.append(construir_regla(solicitud, mapa_objetos))
 
        except (ValueError, KeyError, TypeError) as error:
            print(f"[ERROR] Fila {solicitud.get('fila_excel', '?')}: {error}")
 
    return reglas
 
 
def mostrar_advertencias(grupos):
    """Warnings de seguridad de las reglas que se van a crear."""

    con_avisos = [g for g in grupos if g.get("advertencias")]

    if not con_avisos:
        return

    print("\n--- WARNINGS DE SEGURIDAD (revisar antes de crear) ---")

    for grupo in con_avisos:
        print(f"\nFILA-{grupo['fila_excel']}")
        for advertencia in grupo["advertencias"]:
            print(f"  WARNING - {advertencia}")


def dry_run(reglas):
 
    print("\n--- DRY RUN REGLAS ---")
 
    for regla in reglas:
        print(json.dumps(regla, indent=2, ensure_ascii=False))
 
    print(f"\n[INFO] Reglas listas: {len(reglas)}")
 
 
def crear_politicas(reglas):
 
    if not reglas:
        print("\n[INFO] No hay reglas para crear.")
        return
 
    print("\n--- POLÍTICAS A CREAR ---")
    for regla in reglas:
        print(f"  {regla['name']}")
 
    confirmacion = input(
        f"\n¿Crear estas {len(reglas)} políticas en el FortiGate "
        f"(quedan con estado '{ESTADO_POLITICA}')? (si/no): "
    ).strip().lower()
 
    if confirmacion != "si":
        print("[INFO] Creación de políticas cancelada.")
        return
 
    for regla in reglas:
 
        try:
            if forti_api.crear_politica(regla):
                print(f"[OK] Política creada: {regla['name']}")
            else:
                print(f"[INFO] La política ya existe: {regla['name']}")
 
        except ERRORES_API as error:
            print(f"[ERROR] No se pudo crear {regla['name']}: {error}")
 

# --------------------------------------------------
# 4. CONSULTAR POLÍTICAS EXISTENTES
# --------------------------------------------------

def _nombres(lista):
    """[{'name': 'a'}, {'name': 'b'}] -> 'a, b'"""
    return ", ".join(item.get("name", "?") for item in lista or []) or "-"


def filtrar_politicas(politicas, texto=""):
    """Deja solo las políticas donde aparece el texto (nombre, objeto, servicio...)."""

    texto = texto.strip().lower()

    if not texto:
        return politicas

    campos = ("srcintf", "dstintf", "srcaddr", "dstaddr", "service")

    return [
        p for p in politicas
        if texto in str(p.get("policyid", "")).lower()
        or texto in str(p.get("name", "")).lower()
        or any(texto in _nombres(p.get(campo)).lower() for campo in campos)
    ]


def mostrar_politicas(politicas):

    print("\n--- POLÍTICAS EN EL FORTI ---")

    if not politicas:
        print("[INFO] No hay políticas que mostrar.")
        return

    for p in politicas:

        estado = "ACTIVA" if p.get("status", "enable") == "enable" else "DESHABILITADA"

        print(
            f"\n[{p.get('policyid', '?')}] {p.get('name') or '(sin nombre)'}"
            f"  ->  {p.get('action', '?').upper()} / {estado}"
        )
        print(f"  Interfaces: {_nombres(p.get('srcintf'))} -> {_nombres(p.get('dstintf'))}")
        print(f"  Origen:     {_nombres(p.get('srcaddr'))}")
        print(f"  Destino:    {_nombres(p.get('dstaddr'))}")
        print(f"  Servicios:  {_nombres(p.get('service'))}")

        if p.get("comments"):
            print(f"  Comentario: {p['comments']}")

    activas = sum(p.get("status", "enable") == "enable" for p in politicas)
    print(
        f"\n[INFO] Políticas mostradas: {len(politicas)} "
        f"({activas} activas, {len(politicas) - activas} deshabilitadas)"
    )