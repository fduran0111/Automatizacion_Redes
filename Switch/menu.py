from config_sw import crearvlan, asignar_interfaz_vland, puerto_trunk, channel_group, ver_vlans_detalle
from netmiko import ConnectHandler
from dotenv import load_dotenv
import os
load_dotenv()
switch = {
    "device_type": "cisco_ios_telnet",
    "host": os.getenv("SW_HOST"),
    "username": os.getenv("SW_USER"),
    "password": os.getenv("SW_PASSWORD"),
    "port":int(os.getenv("SW_PORT"))
}
 

 
 
def main():
    print("procesando la conection papi")
    try:
        connection = ConnectHandler(**switch)
        print("se conecto con el ki")
        while True:
 
            print("""
        =========================
        AUTOMATIZACIÓN
        =========================
 
        1. Crear Vlan
        2. Asignar interfaces
        3. Consultar vlan
        0. Salir
        """)
 
            opcion = input("Seleccione: ")
 
            match opcion:
 
                case "1":
                    crearvlan(connection)
 
                case "2":
                    menu_interfaces(connection)
                case "3":
                    ver_vlans_detalle(connection)
                case "0":
                    print("Saliendo...")
                    break
 
                case _:
                    print("Opción inválida")
    except Exception as e:
        print(f"no conecto maldito: {e}")
        return


def menu_interfaces(connection):
    while True:
        print("""
========== CONFIGURAR INTERFACES ==========
 
1. Asignar interfaz a VLAN (Access)
2. Configurar interfaz como Trunk
3. Agregar interfaz a Port-Channel
0. Volver al menú principal
""")
 
        opcion = input("Seleccione una opción: ").strip()
 
        match opcion:
            case "1":
                asignar_interfaz_vland(connection)
 
            case "2":
                puerto_trunk(connection)
 
            case "3":
                channel_group(connection)
 
            case "0":
                break
 
            case _:
                print("Opción inválida.")
 

if __name__ == "__main__":
    main()
 