import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon
import pandas as pd
import json
from shared_components import Sys # Importación de componentes compartidos del sistema
import plotly.express as px
import os
import sys # Importado para manejar argumentos de línea de comandos (sys.argv)

"""
    APLICACIÓN PARA LA GEOLOCALIZACIÓN DE DATOS EN POLÍGONOS A NIVEL AGBR.
    Este script permite la generación de mapas coropléticos interactivos y 
    servicios web para la gestión de datos geográficos.
"""

# Obtiene la ruta absoluta del directorio donde se ejecuta el script para evitar errores de rutas relativas
ACTUAL_PATH = os.path.dirname(os.path.abspath(__file__)) + "/"

# Diccionario de coordenadas predefinidas para centrar el mapa según el ID del estado
centers ={
    15:{"lat":19.3969, "lon": -99.2833} # Coordenadas para el Estado de México
}

def validate_att(att): 
    """
    Valida si un argumento o atributo de texto recibido contiene datos o está vacío.
    :param att: Valor de texto a validar.
    :return: False si está vacío o es un guion, True si tiene contenido válido.
    """
    if att =="" or att =="-":
        return False
    else:
        return True

def validate_bool(att): 
    """
    Valida y convierte un argumento de texto en un valor booleano lógico.
    :param att: Valor de texto (ej. "0" o "1").
    :return: False si el texto es "0", True en cualquier otro caso.
    """
    if att =="0":
        return False
    else:
        return True

def export_figures(fig, outputpath, imagefile_name, title):
    """
    Configura la estética, herramientas interactivas y exporta el mapa a formato HTML.
    :param fig: Objeto figura de Plotly.
    :param outputpath: Directorio de destino.
    :param imagefile_name: Nombre del archivo de salida.
    :param title: Título visible en el mapa.
    """
    # Configuración de la barra de herramientas de Plotly (Modo edición y dibujo)
    config = {'displaylogo': False,
        'editable': True,
        'showLink': True,
        'plotlyServerURL': "https://chart-studio.plotly.com",
        'modeBarButtonsToAdd':['drawline','drawopenpath','drawclosedpath','drawcircle','drawrect','eraseshape']
    }
    # Ajuste de dimensiones y comportamiento del hover (información flotante)
    fig.update_layout(title=title,
                    width=1800,
                    height=1000,
                    hovermode='closest')

    # Generación del archivo HTML interactivo
    fig.write_html("%s/%s.html" % (outputpath,imagefile_name),config=config)

# --- PROCESAMIENTO DE ARGUMENTOS DE LÍNEA DE COMANDOS ---
# Ejemplo de uso: python3 Map.py 01_base_integrada.csv ./output "cvegeo" "etiqueta" "casos" "15" "Mi Titulo"
if len(sys.argv) > 1:
    inputpath = sys.argv[1]      # Archivo CSV de entrada con datos estadísticos
    outputpath = sys.argv[2]     # Ruta de salida para el mapa
    geocve_column = sys.argv[3]  # Columna que vincula el CSV con el ID del mapa (CVEGEO)
    string_label= sys.argv[4]    # Columna para mostrar texto en el hover
    label_color = sys.argv[5]    # Columna numérica que define el color del polígono
    area = sys.argv[6]           # ID del estado (1-32) para cargar el GeoJSON adecuado
    title = sys.argv[7]          # Título principal del mapa

    # Si no se especifica etiqueta para el hover, se usa la clave geográfica por defecto
    if not validate_att(string_label):
        string_label = geocve_column

    print("leyendo geojson")
    # Carga del archivo geográfico JSON basado en el área seleccionada
    geo = json.load(open("%s/GEOJSONS/%sa.json" % (ACTUAL_PATH,area) ,"r"))
    # Lectura del archivo de datos estadísticos
    df = pd.read_csv(inputpath)

    print("creando mapa")
    # Configuración del centro y zoom del mapa según el área
    try:
        cent = centers[int(area)]
        zoom = 9 
    except Exception as e:
        # Valores por defecto si el ID del área no está en el diccionario 'centers'
        cent = {"lat": 19.4326, "lon": -99.1332} 
        zoom = 3

    # Obtención de los IDs geográficos únicos presentes en el CSV
    wanted = df[geocve_column].unique()
    print(f"Registros en datos: {len(wanted)}")
    print(f"Polígonos originales: {len(geo['features'])}")

    # FILTRADO: Se mantienen solo los polígonos del GeoJSON que tienen datos en el CSV
    # Esto optimiza el rendimiento del mapa final al no renderizar áreas vacías
    filtered = [g for g in geo['features'] if g['properties']['CVEGEO'] in wanted]
    geo['features'] = filtered
    print(f"Polígonos filtrados: {len(filtered)}")

    # Creación del mapa coroplético interactivo con Mapbox
    fig = px.choropleth_mapbox(df, geojson=geo, locations=geocve_column, 
                            featureidkey="properties.CVEGEO", # Ruta al ID dentro del GeoJSON
                            color_continuous_scale="Viridis",
                            hover_name=string_label,
                            zoom=zoom,
                            center = cent,
                            mapbox_style="carto-positron",
                            color=label_color,
                            opacity=0.5)

    # Llamada a la función de exportación
    export_figures(fig,outputpath,"mapa",title)

# --- BLOQUE DE SERVIDOR WEB (FLASK) ---
# Nota: Este bloque está comentado en el original para separar el uso de script del uso de API
"""
from flask import Flask, request
app = Flask(__name__)

# Ruta base para verificar que el servicio está corriendo
@app.route('/')
def prueba():
    return {"status":"OK","message":"shapes"}

@app.route('/CreateJSONS')
def createjsons():
    # Lee archivos Shapefile para convertirlos en catálogos JSON ligeros
    df = gpd.read_file("Shapes/15mun_wgs84.shp")
    df['centroid']=''
    
    def coord_lister(row):
        # Procesa geometrías complejas (MultiPolygon)
        if isinstance(row.geometry, MultiPolygon):
            list_of_polys = []
            for poly in row.geometry.geoms:
                list_points= []
                for p in poly.exterior.coords:
                    # Invierte el orden de coordenadas para compatibilidad (lat, lng)
                    list_points.append({"lat":p[0],"lng":p[1]})
                list_of_polys.append(list_points)
            
            # Calcula el centroide para colocar marcadores o etiquetas
            row.centroid = {"lat":row.geometry.centroid.x,"lng":row.geometry.centroid.y}
            row.geometry = list_of_polys
            
        # Procesa geometrías simples (Polygon)
        else:
            list_points= []
            for p in row.geometry.exterior.coords:
                list_points.append({"lat":p[0],"lng":p[1]})
            row.centroid = {"lat":row.geometry.centroid.x,"lng":row.geometry.centroid.y}
            row.geometry = list_points
        return row

    # Aplica la transformación a cada fila del GeoDataFrame
    coordinates = df.apply(coord_lister,axis=1)
    # Exporta catálogos de polígonos y centroides para el frontend
    coordinates[['cvegeo','nomgeo','geometry']].to_json("catalogs/polygon_15mun.json",orient="columns")
    coordinates[['cvegeo','nomgeo','centroid']].to_json("catalogs/centroid_15mun.json",orient="columns")

    return {"status":"OK","message":"shapes"}

@app.route('/getPolygon',methods=['POST'])
def get_agbs():
    # Servicio para obtener polígonos específicos mediante una petición POST
    params = request.get_json(force=True)
    print(params['states'])
    return json.load(open("catalogs/15mun.json", "r") )

if __name__ == '__main__':
    # Ejecuta el servidor en modo debug en el puerto 5555
    app.run(host= '0.0.0.0',port=5555,debug=True)
"""


