"""
Generación de mapas geoespaciales.

Este sricpt permite generar mapas interactivos de tipo heatmap y clustermap
a partir de coordenadas geográficas y variables numéricas, estos datos se
cargar a desde un archivo CSV. Los mapas se exportan en formato
HTML para su visualización en nevegador.

Dependencias:
    -pandas
    -os
    -imageio
    -branca
    -numpy
    -sys
"""
# --- LIBRERIAS ---

# Manipulación y análisis de datos estructurados
import pandas as pd
# Permite interactuar con el sistema operativo (rutas, archivos, directorios)
import os
# Se usa para leer y escribir datos de imágenes y videos
import imageio
# Crear elementos HTML/CSS, usado en mapas interactivos
import branca
# Genera escalas de colores para la visualización de los datos
import branca.colormap as cm
# Proporciona soporte para arreglos y operaciones matemáticas de nivel alto
import numpy as np 

# Importa el componente Sys desde el módulo compartido para reutilizar funciones o utilidades comunes del proyecto
import sys
# Módulo para registrar eventos durante la ejecución del programa
import logging #logger
LOGER = logging.getLogger()

# --- PARÁMETROS ---

# Archivo CSV de entrada, contiene los datos que se van a analizar
INPUT_DATA = sys.argv[1] #"tm_labeled.csv"
# Ruta donde se guardarán los resultados
OUTPUT_PATH = sys.argv[2] #"./results/"
# Tipo de mapa que se generaá, en este caso 1 (heatmap o mapa de calor)
MapType= int(sys.argv[3]) #1 # 1=heatmap, 2= clustermap
# Columnas de coordenadas de latitud y longitud, respectivamente
LAT_COLUMN = sys.argv[4] #"lat"
LON_COLUMN = sys.argv[5] #"lon"
# Columna para agrupar datos
GROUPBY_COLUMN= sys.argv[6] #"anio_regis"
# Variables a analizar (en una lista separada por comas)
VARIABLE = sys.argv[7].split(",") #"Tras. ment. & Uso sust._Hombre_Sexo,Otra causa_Mujer_Sexo".split(",")
# Columna de clasificación que diferencia los datos
CLASS_COLUMN = sys.argv[8] #"class"
# Indica si se normalizan los datos (1 = sí, 0 = no)
NORMALIZE =int(sys.argv[9]) #"0 1
# Etiqueta para identificar cada punto en el mapa
LABEL = sys.argv[10] #label to identify the point

# --- FUNCIONES ---

# Lista de colores disponibles para la visualización
COLORS = [
    'red',
    'blue',
    'gray',
    'darkred',
    'lightred',
    'orange',
    'beige',
    'green',
    'darkgreen',
    'lightgreen',
    'darkblue',
    'lightblue',
    'purple',
    'darkpurple',
    'pink',
    'cadetblue',
    'lightgray',
    'black'
]
# Normaliza (conviertir los datos a una misma escala) 
# los valores de un DataFrame en un rango de 0 a 1.
def normalize(df):
    """
    Normaliza los valores de un DataFrame o Serie en un rango de 0 a 1.

    La normalización se realiza mediante la fórmula:
        (valor - minimo) / (máximo - mínimo)


    """
    # Se crea una copia para evitar modificar el DataFrame original
    result = df.copy()
    # Se obtienen los valores máximo y mínimo
    max_value = df.max()
    min_value = df.min()
    # Se aplica la fórmula de normalización
    result = (df - min_value) / (max_value - min_value)

    return result


def plot_maps(df):
    """
    Genera los mapas interactivos a partir de un DataFrame.

    Dependiendo del valor de ``MapType``, se generará:
        - Heatmap (Mapa de calor)
        - Clustermap (Mapa de clasificación o agrupamiento)
    """
    # Se obtiene el valor del grupo actual (si existe)
    if GROUPBY_COLUMN != "":
        gb_c = df[GROUPBY_COLUMN].iloc[0]
    else:
        gb_c = "all"

    # Se genera un mapa por cada variable
    for v in VARIABLE:
        # Se crea una carpeta de salida específica para la variable
        out_path = "%s%s/" %(OUTPUT_PATH,v)
        try:    
            os.mkdir(out_path)
        except FileExistsError:
            pass


        # Se calcula el centro del mapa usando la mediana de coordenadas
        locat= [df[LAT_COLUMN].median(), df[LON_COLUMN].median()]
        import folium
        # Se crea el mapa base
        map_layer = folium.Map(location=locat, zoom_start=6, control_scale=True,prefer_canvas=True)

        # Heatmap
        if MapType == 1: #normal map
            """
            Generación del mapa de calor (Heatmap)
            """
            if NORMALIZE==1:
                # Si se activa la normalización, se escalan los datos entre 0 y 1
                df[v] = normalize(df[v])
                q1 = 0
                q2 = .25
                q3 = .5
                q4 = .75
                q5 = 1
            else:
                # Se calculan los cuantiles para definir rangos de color
                q1 = df[v].quantile(0)
                q2 = df[v].quantile(0.25)
                q3 = df[v].quantile(0.5)
                q4 = df[v].quantile(0.75)
                q5 = df[v].quantile(1)

            # Se crea una escala de colores de verde a rojo
            colormap = cm.LinearColormap(colors=['green', 'lightgreen', 'yellow', 'orange','red'],
                            index=[q1,q2,q3,q4,q5], vmin=q1, vmax=q5,
                             caption='%s for %s' %(v,gb_c))

            map_layer.add_child(colormap)

            # Se agregan los puntos al mapa
            for index, location_info in df.iterrows():
                # Si el valor es NaN (Not a Number), se reemplaza por 0
                if np.isnan(location_info[v]):
                    location_info[v] = 0 

                # Se obtiene el color según el valor
                color = colormap(location_info[v])
                # Información que aparece al hacer clic en el punto
                html = "<p>%s</p><br> <p>%s</p>" % (location_info[LABEL],location_info[v])
                iframe = folium.IFrame(html,width=100,height=100)
                popup = folium.Popup(iframe,max_width=100)
                # Se dibuja el punto en el mapa
                t = folium.CircleMarker(location=[location_info[LAT_COLUMN],location_info[LON_COLUMN]],
                                     radius=3,
                                     fill=True,
                                     color=color,
                                     popup=popup,
                                     fill_color=color).add_to(map_layer)

        # Clustermap
        elif MapType == 2: #with class column
            """
            Generación del mapa de clasificación (Clustermap)
            """
            # Se agrupan los datos por la columna de clase
            df_grouped = df.groupby(CLASS_COLUMN)
            # Se obtienen los valores únicos de clase
            COLORS = list(df[CLASS_COLUMN].unique())
            # Se crea un mapa de colores para las clases
            colormap = cm.LinearColormap(colors=['lightblue','red'], index=[min(COLORS),max(COLORS)],vmin=min(COLORS),vmax=max(COLORS))

            # Se recorre cada grupo
            for group_name, df_group in df_grouped: # iterate over each group
                for index, location_info in df_group.iterrows():
                    class_label = location_info[CLASS_COLUMN]
                    # Se ignoran valores inválidos
                    if class_label == "-":
                        pass
                    else:
                        class_label = int(class_label)
                        # Se construye el contenido del popup
                        html = ""
                        for vari in VARIABLE:
                            html+= "<p>%s: %s</p><br>" % (vari,location_info[vari])
                        iframe = folium.IFrame(html,width=100,height=100)
                        popup = folium.Popup(iframe,max_width=100)
                        # Se dibuja el punto con color según la clase
                        t =  folium.CircleMarker(location=[location_info[LAT_COLUMN],location_info[LON_COLUMN]],
                                     radius=4,
                                     fill=True,
                                     color=colormap(class_label),
                                     popup=popup,
                                     fill_color=colormap(class_label)).add_to(map_layer)

                        #folium.Marker([location_info[LAT_COLUMN], location_info[LON_COLUMN]],icon=folium.Icon(color=)).add_to(map_layer)
    
        # Guardar imágen de mapa
        try:
            image_path = '%s%s.html'%(out_path,gb_c)
            LOGER.error("GUARDANDO")
            map_layer.save(image_path)
            del map_layer # libera memoria
            LOGER.error(image_path)
            # En modo clustermap solo se genera un mapa
            if MapType==2:
                break

        except Exception as e:
            LOGER.error("================= NO SE PUDO GUARDAR =======================")

# --- EJECUCIÓN ---

# Lectura del archivo CSV
gdf = pd.read_csv(INPUT_DATA) #read csv


if GROUPBY_COLUMN !="":
    """
    Generación de mapas agrupados.
    """
    gdf.groupby(GROUPBY_COLUMN).apply(plot_maps)
    # Generación de gifs
    print("creating gifs")
    for v in VARIABLE:
        out_path = "%s%s/" %(OUTPUT_PATH,v)
        #create_gif(out_path,v)
else:
    """
    Generación de mapas sin agrupación
    """
    plot_maps(gdf)
    
    
#Esto es nuevo para probar el push

