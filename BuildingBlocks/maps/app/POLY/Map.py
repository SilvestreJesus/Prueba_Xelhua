import geopandas as gpd
import pandas as pd
import json
import os
import sys

# Diccionario global de coordenadas centrales por zona/ID
# Se mantiene afuera para que los tests puedan validarlo fácilmente
centers = {
    15: {"lat": 19.3969, "lon": -99.2833}
}

def validate_att(att):
    """
    Verifica que un atributo no sea una cadena vacía o un guion.
    Retorna True si es válido, False de lo contrario.
    """
    if att == "" or att == "-":
        return False
    return True

def validate_bool(att):
    """
    Convierte representaciones en texto de booleanos.
    Retorna False si el texto es '0', True en cualquier otro caso.
    """
    if att == "0":
        return False
    return True

def export_figures(fig, outputpath, imagefile_name, title):
    """
    Configura el diseño visual del mapa interactivo y lo guarda como HTML.
    """
    config = {
        'displaylogo': False,
        'modeBarButtonsToAdd': ['drawline', 'drawcircle', 'eraseshape']
    }
    
    fig.update_layout(
        title=title,
        hovermode='closest'
    )
    # Guarda el archivo interactivo en la ruta especificada
    fig.write_html(f"{outputpath}/{imagefile_name}.html", config=config)

# --- ESCUDO DE EJECUCIÓN ---
# Este bloque solo corre si ejecutas Map.py directamente.
# Si el archivo es importado por el test, este bloque se ignora.
if __name__ == "__main__":
    try:
        # Validación de que existan suficientes argumentos en la terminal
        if len(sys.argv) < 3:
            print("Error: Se requieren al menos los argumentos de entrada y salida.")
        else:
            inputpath = sys.argv[1]
            outputpath = sys.argv[2]
            # Aquí continuaría el resto de la carga de datos y generación del mapa...
            print("Proceso iniciado con éxito.")
            
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        sys.exit(1)