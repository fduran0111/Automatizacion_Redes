import os
import requests
import urllib3
from dotenv import load_dotenv
 
load_dotenv()
 
# El FortiGate suele usar certificado autofirmado (laboratorio)
VERIFY_SSL = False
TIMEOUT = 20
 
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
 
 
def _env(*nombres):
    """Devuelve la primera variable del .env que exista (acepta nombres alternativos)."""
    for nombre in nombres:
        valor = os.getenv(nombre)
        if valor and valor.strip():
            return valor.strip()
    return ""
 
 
HOST = _env("FORTI_HOST", "FORTIGATE_IP").rstrip("/")
TOKEN = _env("FORTI_KEY", "FORTI_TOKEN")
VDOM = _env("FORTI_VDOM")
 
# Acepta el host con o sin "https://"
if HOST and not HOST.startswith(("http://", "https://")):
    HOST = "https://" + HOST
 
 
class FortiError(Exception):
    """Error devuelto por el FortiGate o por la configuración."""
 
 
# Errores que puede lanzar cualquier llamada a la API
ERRORES = (requests.exceptions.RequestException, FortiError)
 
 
def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
 
 
def _params(extra=None):
    params = dict(extra or {})
    if VDOM:
        params["vdom"] = VDOM
    return params
 
 
def _validar_config():
    if not HOST or not TOKEN:
        raise FortiError(
            "Falta FORTI_HOST / FORTI_KEY en el archivo .env"
        )
 
 
# --------------------------------------------------
# Llamadas genéricas
# --------------------------------------------------
 
def consultar_cmdb(recurso, params=None):
    """GET sobre /api/v2/cmdb/<recurso> (solo lectura)."""
 
    _validar_config()
 
    respuesta = requests.get(
        f"{HOST}/api/v2/cmdb/{recurso}",
        headers=_headers(),
        params=_params(params),
        verify=VERIFY_SSL,
        timeout=TIMEOUT,
    )
    respuesta.raise_for_status()
 
    resultado = respuesta.json()
 
    if resultado.get("status") == "error":
        raise FortiError(f"El FortiGate informó un error: {resultado}")
 
    return resultado
 
 
def crear_en_cmdb(recurso, datos):
    """POST sobre /api/v2/cmdb/<recurso>. Lanza FortiError si falla."""
 
    _validar_config()
 
    respuesta = requests.post(
        f"{HOST}/api/v2/cmdb/{recurso}",
        headers=_headers(),
        params=_params(),
        json=datos,
        verify=VERIFY_SSL,
        timeout=TIMEOUT,
    )
 
    try:
        resultado = respuesta.json()
    except ValueError:
        resultado = {"respuesta": respuesta.text}
 
    if respuesta.ok and resultado.get("status", "success") == "success":
        return resultado
 
    raise FortiError(
        f"No se pudo crear en {recurso} "
        f"(HTTP {respuesta.status_code}): {resultado}"
    )
 
 
# --------------------------------------------------
# Consultas
# --------------------------------------------------
 
def obtener_direcciones():
    return consultar_cmdb("firewall/address").get("results", [])
 
 
def obtener_servicios():
    return consultar_cmdb("firewall.service/custom").get("results", [])
 
 
def obtener_grupos_servicio():
    return consultar_cmdb("firewall.service/group").get("results", [])
 
 
def obtener_interfaces():
    return consultar_cmdb("system/interface").get("results", [])
 
 
def obtener_politicas():
    return consultar_cmdb("firewall/policy").get("results", [])
 
 
# --------------------------------------------------
# Creación
# --------------------------------------------------
 
def crear_direccion(objeto):
    return crear_en_cmdb("firewall/address", objeto)
 
 
def crear_politica(regla):
    """Crea la política. Devuelve True si la creó, False si ya existía por nombre."""
 
    politicas = obtener_politicas()
 
    if any(p.get("name") == regla["name"] for p in politicas):
        return False
 
    ids = [
        int(p["policyid"])
        for p in politicas
        if str(p.get("policyid", "")).isdigit()
    ]
 
    regla = {**regla, "policyid": max(ids, default=0) + 1}
 
    crear_en_cmdb("firewall/policy", regla)
    return True