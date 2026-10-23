from netmiko import ConnectHandler
import os 
import re
from dotenv import load_dotenv
from revision import obtener_vlans, obtener_interface, limpiar_interfaz, interfaz_existe, interfaz_libre, vlan_existente, trunk_existente, vlans_con_error, grupo_valido, grupo_existente, grupo_de_interfaz
switch = {
    'device_type': 'cisco_ios_telnet',
    'host': os.getenv('SW_HOST'),
    'username': os.getenv('SW_USER'),
    'password': os.getenv('SW_PASSWORD'),
    'port': os.getenv('SW_PORT')
}

def vlan_existente(vlans, vlan_id):
    for vlan in vlans:
        if vlan["VLAN_ID"] == str(vlan_id):
            return True
    return False

def verinterfaces(net_connect):
    comandos = net_connect.send_command('show interface status')
    print(comandos)

def crearvlan(net_connect):
    while True:
        vlan_id = input("Ingrese el ID de la VLAN (1-4094): ")
        if vlan_id.isdigit() and 1 <= int(vlan_id) <= 4094:
            break
        else:
            print("ID de VLAN inválido. Por favor, ingrese un número entre 1 y 4094.")
    
    vlans = obtener_vlans(net_connect) 
    if vlan_existente(vlans, vlan_id):
        print(f"La VLAN {vlan_id} ya existe. Por favor, ingrese un ID diferente.")
        return crearvlan(net_connect) 
    vlan_name = input("Ingrese el nombre de la VLAN: ")
    comandos = net_connect.send_config_set([f'vlan {vlan_id}', f'name {vlan_name}'])
    net_connect.save_config()
    print(f"VLAN {vlan_id} - {vlan_name} creada con éxito.")


def asignar_interfaz_vland(net_connect):
    interface = limpiar_interfaz(input("Ingrese la interfaz que quiere configurar: "))
    interfaces = obtener_interface(net_connect)

    if not interfaz_existe(interfaces, interface):
        print(f"la interfaz {interface} no existe...")
        return asignar_interfaz_vland(net_connect)
    if not interfaz_libre(interfaces, interface):
        print(f"la interfaz {interface} ya tiene una vlan asignada...")
        return asignar_interfaz_vland(net_connect)

    vlan_id = input("Ingrese el ID de la VLAN a asignar: ").strip()
    vlans = obtener_vlans(net_connect)
    if not vlan_existente(vlans, vlan_id):
        print(f"La VLAN {vlan_id} no existe. Por favor, cree la VLAN primero.")
        return asignar_interfaz_vland(net_connect)

    comandos = net_connect.send_config_set([f'interface {interface}', 'switchport mode access', f'switchport access vlan {vlan_id}'])
    net_connect.save_config()
    print(f"Interfaz {interface} asignada a la VLAN {vlan_id} con éxito.")


def puerto_trunk(net_connect):
    interface = input("Ingrese la interfaz que quiere configurar como trunk: ").strip().replace(" ", "")
    interfaces = obtener_interface(net_connect)

    if not interfaz_existe(interfaces, interface):
        print(f"la interfaz {interface} no existe...")
        return puerto_trunk(net_connect)

    es_trunk = trunk_existente(net_connect, interface)

    if es_trunk:
        print(f"{interface} ya es trunk, se agregarán las VLANs a las que ya tiene permitidas.")
    elif not interfaz_libre(interfaces, interface):
        print(f"la interfaz {interface} ya tiene una vlan asignada...")
        return puerto_trunk(net_connect)

    vlans = input("Ingrese las VLANs que quiere permitir en el trunk (ej: 10,20): ").replace(" ", "")
    errores = vlans_con_error(obtener_vlans(net_connect), vlans)
    if errores:
        for e in errores:
            print(e)
        return puerto_trunk(net_connect)

    if es_trunk:
        config = [f'interface {interface}', f'switchport trunk allowed vlan add {vlans}']
        mensaje = f"VLANs {vlans} agregadas al trunk {interface}."
    else:
        config = [f'interface {interface}', 'switchport mode trunk', f'switchport trunk allowed vlan {vlans}']
        mensaje = f"Interfaz {interface} configurada como trunk con las VLANs {vlans}."

    net_connect.send_config_set(config)
    net_connect.save_config()
    print(mensaje)

def channel_group(net_connect):
    interface = input("ingrese la interfaz que quiere ingresar: ").strip().replace(" ", "")
    interfaces = obtener_interface(net_connect)

    if not interfaz_existe(interfaces, interface):
        print(f"la interfaz {interface} no existe...")
        return channel_group(net_connect)
    if interface.lower().startswith("po"):
        print("esa es una interfaz Port-channel, ingresa un puerto físico (ej: fa0/7)...")
        return channel_group(net_connect)
    grupo_actual = grupo_de_interfaz(net_connect, interface)
    if grupo_actual:
        print(f"la interfaz {interface} ya pertenece al grupo {grupo_actual}...")
        return channel_group(net_connect)

    agrupar = input("ingrese el numero de grupo: ").strip()
    if not grupo_valido(agrupar):
        print("el número de grupo debe ser un entero entre 1 y 6...")
        return channel_group(net_connect)
    if grupo_existente(interfaces, agrupar):
        print(f"el grupo {agrupar} ya existe, la interfaz se sumará a ese grupo.")

    vlans = input("ingrese las vlans que quiere permitir: ").replace(" ", "")
    errores = vlans_con_error(obtener_vlans(net_connect), vlans)
    if errores:
        for e in errores:
            print(e)
        return channel_group(net_connect)

    comandos = net_connect.send_config_set([f'interface {interface}', f'channel-group {agrupar} mode active'])
    net_connect.save_config()
    print(f"interfaz {interface} agregada al grupo {agrupar} correctamente...")
    comandos = net_connect.send_config_set([f'interface Port-channel {agrupar}', 'switchport mode trunk', f'switchport trunk allowed vlan add {vlans}'])
    net_connect.save_config()
    print(f"las vlans {vlans} fueron agregadas al trunk correctamente...")

def ver_vlans_detalle(net_connect):
    vlans = obtener_vlans(net_connect)
    print(f"Total de VLANs: {len(vlans)}\n")

    for v in vlans:
        puertos = re.findall(r"[\w/]+", v["PORTS"])
        print(f"VLAN {v['VLAN_ID']}")
        print(f"  Nombre : {v['NAME']}")
        print(f"  Estado : {v['STATUS']}")
        print(f"  Puertos: {', '.join(puertos) if puertos else '(ninguno)'}  [{len(puertos)}]")
        print("-" * 40)

    