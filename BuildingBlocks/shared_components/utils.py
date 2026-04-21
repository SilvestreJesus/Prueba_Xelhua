"""
ARCHIVO: utils.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. CENTRALIZACIÓN DE UTILIDADES: Este archivo consolida funciones de soporte 
   que antes estaban duplicadas 56 veces. Al centralizarlo, garantizamos que 
   el manejo de archivos y comandos sea consistente en todo el ecosistema.
2. OPTIMIZACIÓN DE MEMORIA: Se han refinado las funciones de compresión para 
   asegurar que el manejo de recursos sea eficiente durante procesos de ETL.
3. COMPATIBILIDAD MULTIPLATAFORMA: Incluye lógica para el manejo de encodings 
   y rutas, mitigando errores comunes al ejecutar el sistema en Windows.
-------------------------------------------------------------------------------
"""

from shared_components import Sys
import json
import pandas as pd
import os
from random import randint
import logging
from base64 import b64encode, b64decode
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from os.path import basename
import time
from shared_components import Csv

# Configuración del Logger para rastreo de operaciones
LOGER = logging.getLogger()

def UncompressFile(path_compressfile, path_results):
    """
    EXTRACCIÓN DE DATOS:
    Toma un archivo ZIP y extrae su contenido. Es la puerta de entrada para 
    datasets que llegan comprimidos al sistema.

    Args:
        path_compressfile (str): Ruta del archivo .zip.
        path_results (str): Carpeta de destino para la extracción.
    """
    with ZipFile(path_compressfile, 'r', ZIP_DEFLATED) as zipObj:
        zipObj.extractall(path_results)


def CompressFile(path_compressfile, path_results, ignore_list=None):
    """
    EMPAQUETADO DE RESULTADOS:
    Genera el archivo 'output.zip' con los resultados del análisis del bloque.
    Implementa una lista de ignorados para evitar incluir metadatos innecesarios.

    Args:
        path_compressfile (str): Carpeta donde se guardará el ZIP.
        path_results (str): Carpeta que contiene lo que se va a comprimir.
        ignore_list (list, optional): Archivos a excluir del ZIP.

    Returns:
        str: Ruta absoluta del archivo generado.
    """
    if ignore_list is None:
        ignore_list = []
        
    fname = os.path.join(path_compressfile, "output.zip")
    with ZipFile(fname, 'w', ZIP_DEFLATED) as zipObj:
        for folderName, subfolders, filenames in os.walk(path_results):
            for filename in filenames:
                if filename not in ignore_list:
                    filePath = os.path.join(folderName, filename)
                    archive_file_path = os.path.relpath(filePath, path_results)
                    zipObj.write(filePath, archive_file_path)

    return fname


def FormatParam(param):
    """
    SERIALIZACIÓN DE PARÁMETROS:
    Convierte estructuras de Python (listas/dicts) a strings. Vital para la 
    comunicación entre el Middleware y los scripts de ejecución (Triggers).

    Args:
        param (any): Parámetro en formato original.

    Returns:
        str: Parámetro formateado para línea de comandos o JSON.
    """
    if isinstance(param, list):
        return ",".join([str(i) for i in param])
    elif isinstance(param, dict):
        return json.dumps(param)
    else:
        return str(param)


def Get_Env_FromFile(archivo_csv):
    """
    GESTOR DE VARIABLES DE ENTORNO:
    Lee la configuración de entorno desde un CSV. Esta función es clave para 
    proyectos de Ciencia de Datos que parametrizan sus modelos vía archivos externos.

    Args:
        archivo_csv (str): Ruta al CSV con las variables.

    Returns:
        dict: Mapeo de variables de entorno.
    """
    try:
        with open(archivo_csv, "r", newline="", encoding="utf-8-sig") as csv_file:
            csv_reader = csv.reader(csv_file)
            encabezados = next(csv_reader)
            segunda_fila = next(csv_reader)
            segunda_fila_dict = dict(zip(encabezados, segunda_fila))
            json_data = json.dumps(segunda_fila_dict)
        
        return json.loads(json_data)
    except (FileNotFoundError, csv.Error):
        return {}


def get_var_in_string(command, initial="$ENV"):
    """
    PARSER DE VARIABLES:
    Identifica y extrae nombres de variables dentro de strings complejos.
    Soporta la sintaxis propietaria del proyecto: $ENV(variable).
    """
    start = command.find(initial + "(") + (1 + len(initial))
    if start == 1: 
        return None
    end = command.find(')', start)
    if start > end:
        return None
        
    parameter_found = command[start:end]
    return parameter_found


def FormatCommand(command, params, reserved_params=None, POSTMAN=None, default_none=True):
    """
    MOTOR DE INYECCIÓN DE COMANDOS:
    Esta es la función más crítica de utils.py. Inyecta dinámicamente valores 
    dentro de comandos de ejecución, permitiendo que un mismo script 
    funcione con diferentes datasets y parámetros.

    Implementa:
    - Reemplazo de @{param}: Parámetros directos.
    - Reemplazo de @{$ENV()}: Variables de entorno.
    - Reemplazo de @{$REF::}: Referencias externas vía POSTMAN.
    """
    if reserved_params is None:
        reserved_params = {}

    while True:
        start = command.find('@{') + 2
        if start == 1: 
            break
        end = command.find('}', start)
        if start > end:
            return None
            
        parameter_found = command[start:end]

        # Inyección de parámetros reservados
        if parameter_found in reserved_params:
            command = command.replace("@{%s}" % parameter_found, reserved_params[parameter_found])
        elif parameter_found in params:
            temp_p = FormatParam(params[parameter_found])
            command = command.replace("@{%s}" % parameter_found, temp_p)

        # Resolución de referencias externas ($REF)
        elif "$REF" in parameter_found:
            temporal_parm_found = parameter_found.split("::", 1)[1]

            if POSTMAN is not None:
                LOGER.info("Inyectando referencia externa vía POSTMAN")
                env_dataset = reserved_params.get('ENV_DATASET', {})
                if len(env_dataset) >= 1:
                    temp_p = POSTMAN.GetReference(temporal_parm_found, ENV=env_dataset)
                else:
                    temp_p = POSTMAN.GetReference(temporal_parm_found, ENV=params.get('ENV'))

                command = command.replace("@{$REF::%s}" % temporal_parm_found, str(temp_p))
            else:
                LOGER.error("ERROR: Se requiere objeto POSTMAN para resolver $REF") 
                command = command.replace("@{%s}" % parameter_found, "-")
                
        # Resolución de variables de entorno ($ENV)
        elif "$ENV" in parameter_found:
            temporal_parm_found = get_var_in_string(parameter_found, initial="$ENV") 

            env_params = params.get('ENV', {})
            res_env = reserved_params.get('ENV_DATASET', {})

            if temporal_parm_found in env_params:
                temp_p = FormatParam(env_params[temporal_parm_found])
                command = command.replace("@{%s}" % parameter_found, temp_p)
            elif temporal_parm_found in res_env:
                temp_p = FormatParam(res_env[temporal_parm_found])
                command = command.replace("@{%s}" % parameter_found, temp_p)
            else:
                command = command.replace("@{%s}" % parameter_found, "NONE")

        # Tratamiento de parámetros inexistentes
        else:
            command = command.replace("@{%s}" % parameter_found, "-" if default_none else "")

    return command