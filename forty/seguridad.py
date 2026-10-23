import ipaddress
import json
from pathlib import Path
 
BASE = Path(__file__).parent
RUTA_PUERTO_SEGURIDAD = BASE / "puerto_seguridad.json"
 
ACCIONES = ("permitir", "advertir","bloquear")
SENTIDOS = ("lan","hacia_internet","desde_internet")
 
def cargar_puerto_seguridad(ruta = RUTA_PUERTO_SEGURIDAD):
    #Abrimos el archivo puerto_seguridad.json, si el archivo no contiene nada o si no tiene el formato da error
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            puerto_seguridad = json.load(archivo)
    except FileNotFoundError:
        raise ValueError(f"No existe{Path(ruta).name}.")
    except json.JSONDecodeError as error:
        raise ValueError(f"{Path(ruta).name} no tiene un formato correcto: {error}")
    
    #extraemos las acciones del archivo y las categorias que contiene, las guardamos en el diccionario "acciones_por_categoria"
    acciones_por_categoria = [("por defecto", puerto_seguridad.get("por_defecto", {}))] + list(puerto_seguridad.get("categorias",{}).items())
    #aqui solo verificamos si contiene exactamente las acciones que esta en la variable "ACCIONES"
    for name, acciones in acciones_por_categoria:
        for sentido in SENTIDOS:
            if acciones.get(sentido) not in ACCIONES:
                raise ValueError(
                    f"{Path(ruta).name}: {name} necesita {sentido}"
                    f"con uno de estos valores: {", ".join(ACCIONES)}"
                )
    return puerto_seguridad
 
#funcion para clasificar si una ip es internet o lan
def clasificar_ip(direccion):
 
    red = ipaddress.ip_network(direccion, strict=False)
 
    if red.is_multicast:
        return "LAN"
 
    return "INTERNET" if red.is_global else "LAN"
 
# funcion que clasifica si la zona de direcciones es internet o lan
def zona(direcciones):
 
    zonas = {clasificar_ip(s) for s in direcciones}
    return "INTERNET" if "INTERNET" in zonas else "LAN"
 
#funcion que identifica si va hacia internet, desde internet o es lan
def sentido_de (origenes, destinos):
 
    origen, destino = zona(origenes), zona(destinos)
    sentido = []
 
    if destino == "INTERNET":
        sentido.append("hacia_internet")
    elif origen == "INTERNET":
        sentido.append("desde_internet")
    if not sentido:
        sentido.append("lan")
    return origen, destino, sentido
 
#Funcion que extrae los servicios del excel y ve si esta dentro un grupo de servicios y los separa por servicios individuales, si no muestra el servicio solo
def expandir(servicios, datos, vistos=None):
 
    vistos = vistos or set()
    if servicios in vistos:
        return []
    vistos.add(servicios)
 
    entrada = datos.get(servicios, {})
    if "grupo" not in entrada:
        return {servicios}
    miembros = []
    for miembro in entrada ["grupo"]:
        miembros += expandir(miembro,datos,vistos)
    return miembros
 
#aqui dejamos el mismo formato que ocupa nuestro JSON  
def puertos_de(entrada):
             
    return {
        f"{proto}/{puerto}"
        for proto in ("tcp","udp","sctp")
        for puerto in entrada.get(proto,[])
        if isinstance(puerto, int)
    }
# aqui sacamos la categoria de los servicios o servicio (kerberos - categoria = Windows interno)
def categorias_de(servicio, datos, puerto_seguridad):
    nombre = servicio.upper() #aqui pasa cada puerto de la llamada de esta funcion a mayuscula
    puertos = puertos_de(datos.get(servicio, [])) # aqui datos es el catalogo de puerto.json, .get(servicio, []) aqui rescatamos si esta el servicio que nos llego si no devuelve una lista vacio
    categorias = []
    for categoria, acciones in puerto_seguridad["categorias"].items():
        if nombre in (s.upper() for s in acciones.get("servicios", [])) or puertos & set(acciones.get("puertos", [])):
            categorias.append(categoria)   # aqui guardamos en una lista las categorias de cada servicio, para asi poder identificar si por servicio y categoria daria un warning
    return categorias
 
 
# aqui esta la funcion que recopila todo, para identificar los origen, destino y servicios para detectar warning
 
def evaluar (origenes, destinos, servicios, datos, puerto_seguridad):
 
    if not origenes or not destinos or not servicios:
        return [], []
 
    origen, destino, sentidos = sentido_de(origenes, destinos) #vemos el sentido de donde viene nuestro origen/es y destino/s
    trayecto = f"{origen} -> {destino}" #variable para mostrar en pantalla
 
    errores, advertencias = [], []
 
    if origen == "INTERNET" and destino == "INTERNET":
        advertencias.append(f"origen y destino en internet {trayecto}. revisar")
    if zona(destinos) == "INTERNET" and len({clasificar_ip(i) for i in destinos}) > 1:
        advertencias.append(f"en destino existe LAN y INTERNET en la misma fila, revisar")
 
    for servicio in servicios:
        for real in expandir(servicio, datos): #real va tomar el valor de que venga de vuelta de la funcion expandir, si servicio es un grupo(email access), real sera (DNS", "IMAP",etc)
            categorias = categorias_de(real, datos, puerto_seguridad)
            if real != servicio:
                via = f"(dentro de {servicio})"
            else:
                via = ""
            acciones_por_categoria = []
            #obtenemos las acciones de cada categoria
            for c in categorias:
                configuracion_accion= puerto_seguridad["categorias"][c] #aqui guardamos la configuracion de las acciones de la categoria: window interno (lan:permitir...)
                acciones_por_categoria.append((c, configuracion_accion))
            if not acciones_por_categoria:
                acciones_por_categoria.append(("sin categoría",puerto_seguridad["por_defecto"]))
       
            for categoria, acciones in acciones_por_categoria:
                 for sentido in sentidos:
                    accion = acciones[sentido] #aqui acciones[sentido] me arroja que si sentido es "hacia internet" y ve si la categoria la permite, me dara permitir, advertir o bloquear
                    texto_info = f"{real}{via} [{categoria}] no permitido en {trayecto}"
                    if accion == "bloquear":
                        errores.append(f"Seguridad: {texto_info}")
                    if accion == "advertir":
                        advertencias.append(f"{real}{via} en {trayecto}, revisar")
    return list(set(errores)), list(set(advertencias)) #elimina errores y advertencias repetidas.