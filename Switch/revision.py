from netmiko import ConnectHandler
import os 
import re  
from dotenv import load_dotenv
import textfsm


def parsear_vlans(salida, plantilla):
    with open(plantilla) as f:
        fsm = textfsm.TextFSM(f)
        return [dict(zip(fsm.header, r)) for r in fsm.ParseText(salida)]
    
def unir_lineas(salida):
    lineas = []
    for l in salida.splitlines():
        if l.startswith(" ") and lineas:
            lineas[-1] += " " + l.strip()
        else:
            lineas.append(l)
    return "\n".join(lineas)

def obtener_vlans (net_connect):
    comandos = net_connect.send_command('show vlan brief')
    return parsear_vlans(unir_lineas(comandos),"show_vlan.textfsm")

def obtener_interface(net_connect):
    comandos = net_connect.send_command('show interface status')
    return parsear_vlans(unir_lineas(comandos),"show_interfaces.textfsm")

def limpiar_interfaz(texto):
    return texto.strip().replace(" ", "")

def interfaz_existe(interfaces, interface):
    return any(i["PORT"].lower() == interface.lower() for i in interfaces)

def interfaz_libre(interfaces, interface):
    return any(i["PORT"].lower() == interface.lower() and i["VLAN"] == "1" for i in interfaces)

def vlan_existente(vlans, vlan_id):
    return any(v["VLAN_ID"] == str(vlan_id) for v in vlans)

def trunk_existente(net_connect, interface):
    salida = net_connect.send_command(f'show interfaces {interface} switchport')
    return "Administrative Mode: trunk" in salida

def vlans_con_error(vlans_existentes, texto):
    errores = []
    for vid in texto.replace(" ", "").split(","):
        if not vid.isdigit() or not (1 <= int(vid) <= 4094):
            errores.append(f"'{vid}' no es un ID válido (1-4094)")
        elif not vlan_existente(vlans_existentes, vid):
            errores.append(f"la VLAN {vid} no existe")
    return errores

def grupo_valido(agrupar):
    return agrupar.isdigit() and 1 <= int(agrupar) <= 6      # el 2960 permite grupos del 1 al 6

def grupo_existente(interfaces, agrupar):
    return any(i["PORT"].lower() == f"po{agrupar}" for i in interfaces)

def grupo_de_interfaz(net_connect, interface):
    salida = net_connect.send_command(f'show running-config interface {interface}')
    m = re.search(r"channel-group (\d+)", salida)
    return m.group(1) if m else None