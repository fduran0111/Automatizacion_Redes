
import json
from pathlib import Path
 
import forti_api
 
BASE = Path(__file__).parent
RUTA_SERVICIOS = BASE / "puerto.json"
 
PROTOCOLOS = ("tcp", "udp", "sctp")
 
 
# --------------------------------------------------
# 1. Forti -> puerto.json
# --------------------------------------------------
 
def _leer_rangos(texto):
    """'443 8000-8080:1024-65535' -> ([443, '8000-8080'], restringido)."""
 
    puertos, restringido = [], False
 
    for token in str(texto or "").split():
 
        destino, _, origen = token.partition(":")
        if origen:
            restringido = True  # limita el puerto de origen
 
        inicio, _, fin = destino.partition("-")
 
        if fin and fin != inicio:
            puertos.append(f"{int(inicio)}-{int(fin)}")
        else:
            puertos.append(int(inicio))
 
    return puertos, restringido
 
 
def convertir_servicio(servicio):
    """Servicio custom del Forti -> entrada de puerto.json."""
 
    protocolo = servicio.get("protocol", "TCP/UDP/SCTP")
 
    if protocolo != "TCP/UDP/SCTP":
        return {"protocolo": protocolo}  # ICMP, IP, ICMP6...
 
    entrada = {}
    restringido = bool(servicio.get("fqdn")) or servicio.get(
        "iprange", "0.0.0.0"
    ) not in ("", "0.0.0.0")
 
    for proto in PROTOCOLOS:
        puertos, limita_origen = _leer_rangos(servicio.get(f"{proto}-portrange"))
        restringido = restringido or limita_origen
        if puertos or proto != "sctp":
            entrada[proto] = puertos
 
    if restringido:
        entrada["restringido"] = True
 
    return entrada
 
 
def sincronizar_servicios(ruta=RUTA_SERVICIOS):
    """Descarga servicios y grupos del Forti y los guarda en puerto.json."""
 
    datos = {
        s["name"]: convertir_servicio(s) for s in forti_api.obtener_servicios()
    }
 
    for grupo in forti_api.obtener_grupos_servicio():
        datos[grupo["name"]] = {
            "grupo": [m["name"] for m in grupo.get("member", [])]
        }
 
    datos = dict(sorted(datos.items(), key=lambda x: x[0].upper()))
 
    # Una línea por servicio para que el archivo se pueda leer a simple vista
    lineas = [
        f"    {json.dumps(nombre, ensure_ascii=False)}: "
        f"{json.dumps(entrada, ensure_ascii=False)}"
        for nombre, entrada in datos.items()
    ]
 
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write("{\n" + ",\n".join(lineas) + "\n}\n")
 
    print(f"[OK] {len(datos)} servicios guardados en {Path(ruta).name}")
 
    return datos
 
 
# --------------------------------------------------
# 2. puerto.json -> catálogo
# --------------------------------------------------
 
def cargar_servicios(ruta=RUTA_SERVICIOS):
 
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except FileNotFoundError:
        raise ValueError(
            f"No existe {Path(ruta).name}. Sincroniza los servicios del Forti primero."
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"{Path(ruta).name} no tiene un formato válido: {error}")
 
    if not isinstance(datos, dict) or not datos:
        raise ValueError(f"{Path(ruta).name} está vacío o mal formado.")
 
    return datos
 
 
def _puertos_exactos(entrada):
    """{(proto, puerto)} si el servicio abre solo puertos sueltos; si no, None."""
 
    if "grupo" in entrada or "protocolo" in entrada or entrada.get("restringido"):
        return None
 
    pares = set()
 
    for proto in PROTOCOLOS:
        for puerto in entrada.get(proto, []):
            if not isinstance(puerto, int):
                return None  # rango
            pares.add((proto, puerto))
 
    return pares or None
 
 
class Catalogo:
    """Traduce nombres y puertos del Excel a servicios que existen en el Forti."""
 
    def __init__(self, datos):
 
        self.datos = datos
        self.nombres = {nombre.upper(): nombre for nombre in datos}
        self.con_espacios = [nombre for nombre in datos if " " in nombre]
        self.exactos = {}
 
        for nombre, entrada in datos.items():
            pares = _puertos_exactos(entrada)
            if pares:
                self.exactos[nombre] = pares
 
    def por_nombre(self, texto):
        return self.nombres.get(texto.strip().upper())
 
    def por_puerto(self, puerto, protocolo=None):
        """Devuelve (nombre, error). nombre=None y error=None => no existe.
 
        Puerto suelto (443): servicios que abren SOLO ese número (en tcp, udp o ambos).
        Con protocolo (514/udp): servicios que abren SOLO ese protocolo/puerto.
        """
 
        if protocolo:
            candidatos = [
                n for n, p in self.exactos.items() if p == {(protocolo, puerto)}
            ]
        else:
            candidatos = [
                n for n, p in self.exactos.items() if {x[1] for x in p} == {puerto}
            ]
 
        if len(candidatos) == 1:
            return candidatos[0], None
 
        if not candidatos:
            return None, None
 
        return None, (
            f"Puerto {puerto} ambiguo: {', '.join(sorted(candidatos))}. "
            "Escribe el nombre del servicio en el Excel."
        )
 
 
def cargar_catalogo(ruta=RUTA_SERVICIOS):
    return Catalogo(cargar_servicios(ruta))
 