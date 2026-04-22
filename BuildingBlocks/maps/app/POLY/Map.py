import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon
import pandas as pd
import json
import os
import sys
import plotly.express as px
from flask import Flask, request

"""
APLICACIÓN PARA LA GEOLOCALIZACIÓN DE DATOS EN POLÍGONOS (NIVEL AGEB / MUNICIPAL)
--------------------------------------------------------------------------------
Este script permite procesar archivos geográficos, cruzar datos estadísticos 
y generar mapas interactivos o servicios web de consulta de polígonos.
"""

# --- CONFIGURACIÓN GLOBAL ---

# Obtiene la ruta absoluta del directorio donde se encuentra este archivo
ACTUAL_PATH = os.path.dirname(os.path.abspath(__file__)) + "/"

# Diccionario de coordenadas para centrar el mapa automáticamente por estado
# Clave: ID del estado (INEGI), Valor: Latitud y Longitud
centers = {
    15: {"lat": 19.3969, "lon": -99.2833}  # Estado de México
}

# --- FUNCIONES DE APOYO Y VALIDACIÓN ---

def validate_att(att):
    """
    Valida si un argumento de entrada contiene datos válidos o está vacío.
    :param att: (str) El atributo a validar.
    :return: (bool) False si es vacío o un guion, True si tiene contenido.
    """
    if att == "" or att == "-":
        return False
    else:
        return True

def validate_bool(att):
    """
    Convierte un valor de texto tipo '0' o '1' a un booleano real.
    :param att: (str) El valor recibido de consola o API.
    :return: (bool) False si el string es "0", True en cualquier otro caso.
    """
    if att == "0":
        return False
    else:
        return True

def export_figures(fig, outputpath, imagefile_name, title):
    """
    Configura el diseño (layout) y exporta el mapa de Plotly a un archivo HTML interactivo.
    :param fig: Objeto de figura de Plotly Express.
    :param outputpath: (str) Carpeta de destino del archivo.
    :param imagefile_name: (str) Nombre del archivo (sin extensión).
    :param title: (str) Título que se mostrará dentro del mapa.
    """
    # Configuración de herramientas de la barra de modo (dibujo, zoom, etc.)
    config = {
        'displaylogo': False,
        'editable': True,
        'showLink': True,
        'plotlyServerURL': "https://chart-studio.plotly.com",
        'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'drawclosedpath', 'drawcircle', 'drawrect', 'eraseshape']
    }
    
    # Actualización de dimensiones y modo de información al pasar el mouse
    fig.update_layout(
        title=title,
        width=1800,
        height=1000,
        hovermode='closest'
    )

    # Generación del archivo físico HTML
    fig.write_html("%s/%s.html" % (outputpath, imagefile_name), config=config)


# --- BLOQUE PRINCIPAL DE EJECUCIÓN (MODO SCRIPT) ---
# Se ejecuta cuando llamas al archivo desde la terminal:
# Ejemplo: python3 Map.py data.csv ./output "cvegeo" "nombre_mun" "total_casos" "15" "Mi Mapa"

if __name__ == "__main__" and len(sys.argv) > 1:
    # 1. Captura de parámetros de línea de comandos
    inputpath = sys.argv[1]      # Ruta del archivo CSV con los datos
    outputpath = sys.argv[2]     # Carpeta donde se guardará el resultado
    geocve_column = sys.argv[3]  # Nombre de la columna ID en el CSV (CVEGEO)
    string_label = sys.argv[4]   # Columna para el texto del hover (etiqueta)
    label_color = sys.argv[5]    # Columna para determinar el color del polígono
    area = sys.argv[6]           # ID de la entidad (ej. "15" para EdoMex)
    title = sys.argv[7]          # Título del mapa

    # Si no se define una etiqueta para el hover, se usa la clave geográfica por defecto
    if not validate_att(string_label):
        string_label = geocve_column

    print("Leyendo archivos geográficos...")
    # Carga del GeoJSON correspondiente al área seleccionada
    geo = json.load(open("%s/GEOJSONS/%sa.json" % (ACTUAL_PATH, area), "r"))
    
    # Carga del CSV de datos estadísticos
    df = pd.read_csv(inputpath)

    print("Configurando centro y zoom del mapa...")
    # Intenta obtener el centro del estado desde el diccionario; si no existe, usa valores por defecto
    try:
        cent = centers[int(area)]
        zoom = 9 
    except Exception as e:
        cent = {"lat": 19.4326, "lon": -99.1332} # CDMX por defecto
        zoom = 3

    # OPTIMIZACIÓN: Filtrado de polígonos
    # Obtenemos los IDs únicos del CSV y filtramos el GeoJSON para que solo tenga esos polígonos
    wanted = df[geocve_column].unique()
    filtered = [g for g in geo['features'] if g['properties']['CVEGEO'] in wanted]
    geo['features'] = filtered

    print(f"Generando mapa coroplético con {len(filtered)} elementos...")
    # Creación del mapa usando Mapbox
    fig = px.choropleth_mapbox(
        df, 
        geojson=geo, 
        locations=geocve_column,            # Columna del DF
        featureidkey="properties.CVEGEO",   # Llave dentro del GeoJSON
        color_continuous_scale="Viridis",   # Escala cromática
        hover_name=string_label,            # Título en el cuadro flotante
        zoom=zoom,
        center=cent,
        mapbox_style="carto-positron",      # Estilo del mapa base
        color=label_color,                  # Variable que define el color
        opacity=0.5                         # Transparencia
    )

    # Exportación final
    export_figures(fig, outputpath, "mapa", title)
    print("Proceso completado.")


# --- SERVIDOR WEB (API FLASK) ---

app = Flask(__name__)

@app.route('/')
def status():
    """Ruta base para verificar que el servicio está activo."""
    return {"status": "OK", "message": "Servicio de geolocalización activo"}

@app.route('/CreateJSONS')
def createjsons():
    """
    Lee un archivo Shapefile (.shp) y genera catálogos JSON optimizados.
    Calcula centroides y extrae coordenadas para uso en aplicaciones web.
    """
    # Lectura del archivo geográfico original
    df_geo = gpd.read_file("Shapes/15mun_wgs84.shp")
    df_geo['centroid'] = ''

    def coord_lister(row):
        """
        Función interna para extraer coordenadas de la geometría de cada fila.
        :param row: Fila del GeoDataFrame.
        """
        # Caso 1: La geometría contiene múltiples polígonos
        if isinstance(row.geometry, MultiPolygon):
            list_of_polys = []
            for poly in row.geometry.geoms:
                list_points = []
                for p in poly.exterior.coords:
                    # Formato amigable para Leaflet/Google Maps (lat, lng)
                    list_points.append({"lat": p[1], "lng": p[0]})
                list_of_polys.append(list_points)
            
            # Cálculo del punto central (centroide)
            row.centroid = {"lat": row.geometry.centroid.y, "lng": row.geometry.centroid.x}
            row.geometry = list_of_polys
            
        # Caso 2: La geometría es un polígono simple
        else:
            list_points = []
            for p in row.geometry.exterior.coords:
                list_points.append({"lat": p[1], "lng": p[0]})
            row.centroid = {"lat": row.geometry.centroid.y, "lng": row.geometry.centroid.x}
            row.geometry = list_points
        return row

    # Aplica la extracción de coordenadas a todo el archivo
    coordinates = df_geo.apply(coord_lister, axis=1)
    
    # Guarda los resultados en archivos JSON para ser consumidos por el Frontend
    coordinates[['cvegeo', 'nomgeo', 'geometry']].to_json("catalogs/polygon_15mun.json", orient="columns")
    coordinates[['cvegeo', 'nomgeo', 'centroid']].to_json("catalogs/centroid_15mun.json", orient="columns")

    return {"status": "OK", "message": "Catálogos generados correctamente"}

@app.route('/getPolygon', methods=['POST'])
def get_agbs():
    """
    Recibe una petición POST y devuelve la geometría municipal almacenada.
    """
    params = request.get_json(force=True)
    # Ejemplo de uso: filtrar por params['states'] si fuera necesario
    return json.load(open("catalogs/15mun.json", "r"))

if __name__ == '__main__':
    # Ejecución del servidor en el puerto 5555
    app.run(host='0.0.0.0', port=5555, debug=True)