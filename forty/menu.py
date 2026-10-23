from pathlib import Path
from revision_excel import generar_excel     
import forti_api
from reglasForti import (
    ERRORES_API,
    agrupar_solicitudes,
    comparar_direcciones,
    construir_reglas,
    crear_objetos_faltantes,
    crear_politicas,
    dry_run,
    filtrar_politicas,
    mapear_objetos_por_ip,
    mostrar_advertencias,
    mostrar_politicas,
)
from servicios import RUTA_SERVICIOS, sincronizar_servicios
from validacion import direcciones_unicas, leer_solicitudes, mostrar_resultados
 
BASE = Path(__file__).parent
 
EXCEL = BASE / "permisos.xlsx"
 
 
# Datos compartidos entre las opciones del menú
estado = {
    "solicitudes": None,
    "objetos": None,
    "faltantes": None,  # direcciones sin objeto en el Forti
    "reglas": None,
}
 
 
def _limpiar_desde_validacion():
    estado["faltantes"] = None
    estado["reglas"] = None
 
 
# --------------------------------------------------
# Pasos
# --------------------------------------------------
 
def paso_sincronizar():
    """1. Descargar los servicios del Forti a puerto.json."""
 
    try:
        sincronizar_servicios()
    except ERRORES_API as error:
        print(f"[ERROR] {error}")
        return False
 
    # Con otro catálogo, la validación anterior ya no sirve
    estado["solicitudes"] = None
    _limpiar_desde_validacion()
    return True
 
 
def paso_validar():
    """2. Leer el Excel y traducir puertos a servicios del Forti."""
 
    if not RUTA_SERVICIOS.exists():
        print("[INFO] No existe puerto.json, se sincroniza primero.")
        if not paso_sincronizar():
            return
 
    estado["solicitudes"] = leer_solicitudes(EXCEL)              # ← 4. solo la ruta del Excel
    mostrar_resultados(estado["solicitudes"])
    _limpiar_desde_validacion()
 
 
def paso_comparar():
    """3. Comparar las IPs del Excel con los objetos del Forti (solo lectura)."""
 
    if estado["solicitudes"] is None:
        paso_validar()
 
    if estado["solicitudes"] is None:
        return
 
    unicas = direcciones_unicas(estado["solicitudes"])
    print("\nDirecciones únicas:", len(unicas))
 
    try:
        estado["objetos"] = forti_api.obtener_direcciones()
    except ERRORES_API as error:
        print(f"[ERROR] {error}")
        estado["faltantes"] = None
        return
 
    estado["faltantes"] = comparar_direcciones(unicas, estado["objetos"])
 
 
def paso_crear_objetos():
    """4. Crear los objetos de dirección que faltan (pide confirmación)."""
 
    if estado["faltantes"] is None:
        paso_comparar()
 
    if estado["faltantes"] is None:
        return
 
    crear_objetos_faltantes(estado["faltantes"])
 
    # Después de crear hay que volver a comparar con el Forti
    if estado["faltantes"]:
        print("\n--- VERIFICACIÓN FINAL ---")
        paso_comparar()
 
 
def paso_dry_run():
    """5. Armar y mostrar las reglas, sin enviar nada."""
 
    if estado["faltantes"] is None:
        paso_comparar()
 
    if estado["faltantes"] is None:
        return
 
    if estado["faltantes"]:
        print(
            f"\n[ERROR] Faltan {len(estado['faltantes'])} objetos en el Forti. "
            "Usa la opción 4 primero."
        )
        return
 
    # Solo entran las filas VALIDADAS (las que tienen todos sus servicios)
    grupos = agrupar_solicitudes(estado["solicitudes"])
    print("\nReglas después de agrupar:", len(grupos))
 
    mapa = mapear_objetos_por_ip(estado["objetos"])
    estado["reglas"] = construir_reglas(grupos, mapa)
    dry_run(estado["reglas"])
    mostrar_advertencias(grupos)
 

def paso_ver_politicas():
    """6. Mostrar las políticas que ya existen en el Forti (solo lectura)."""

    try:
        politicas = forti_api.obtener_politicas()
    except ERRORES_API as error:
        print(f"[ERROR] {error}")
        return

    print(f"\n[INFO] Políticas en el Forti: {len(politicas)}")

    texto = input(
        "Filtrar por nombre, ID, objeto, interfaz o servicio "
        "(Enter = todas): "
    )

    mostrar_politicas(filtrar_politicas(politicas, texto))


def paso_crear_politicas():
    """7. Crear las políticas en el Forti (pide confirmación)."""
 
    if estado["reglas"] is None:
        paso_dry_run()
 
    if estado["reglas"] is None:
        return
 
    crear_politicas(estado["reglas"])


def paso_excel_revision():
    """8. Generar una copia del Excel marcada con lo que hay que corregir."""

    if not RUTA_SERVICIOS.exists():
        print("[INFO] No existe puerto.json, se sincroniza primero.")
        if not paso_sincronizar():
            return

    # Se relee el Excel por si el usuario lo corrigió desde la última validación
    estado["solicitudes"] = leer_solicitudes(EXCEL)              # ← 4. solo la ruta del Excel
    _limpiar_desde_validacion()

    salida = generar_excel(EXCEL, estado["solicitudes"])         # ← 2. tu función, con 2 parámetros

    revisar = sum(s["estado"] != "VALIDADA" for s in estado["solicitudes"])
    print(f"\n[OK] Excel generado: {salida}")                    # ← 3. sin .name
    print(f"[INFO] Filas por revisar: {revisar} de {len(estado['solicitudes'])}")
 

# --------------------------------------------------
# Menú
# --------------------------------------------------
 
OPCIONES = {
    "1": ("Sincronizar servicios del Forti -> puerto.json", paso_sincronizar),
    "2": ("Leer y validar el Excel", paso_validar),
    "3": ("Comparar direcciones con el Forti (solo lectura)", paso_comparar),
    "4": ("Crear objetos faltantes (pide confirmación)", paso_crear_objetos),
    "5": ("Dry-run de reglas (no envía nada)", paso_dry_run),
    "6": ("Ver políticas del Forti (solo lectura)", paso_ver_politicas),
    "7": ("Crear políticas en el Forti (pide confirmación)", paso_crear_politicas),
    "8": ("Generar Excel con las correcciones", paso_excel_revision),
}
 
 
def mostrar_menu():
 
    print("\n" + "=" * 50)
    print("  AUTOMATIZACIÓN FORTIGATE")
    print("=" * 50)
 
    for clave, (texto, _) in OPCIONES.items():
        print(f"  {clave}. {texto}")
 
    print("  0. Salir")
    print("=" * 50)
 
 
def menu():
 
    while True:
 
        mostrar_menu()
        eleccion = input("Elige una opción: ").strip()
 
        if eleccion == "0":
            print("Hasta luego.")
            break
 
        if eleccion not in OPCIONES:
            print("[ERROR] Opción no válida.")
            continue
 
        try:
            OPCIONES[eleccion][1]()
        except (OSError, ValueError, KeyError) as error:
            print(f"[ERROR] {error}")
 
        input("\nPresiona Enter para volver al menú...")
 
 
if __name__ == "__main__":
    menu()