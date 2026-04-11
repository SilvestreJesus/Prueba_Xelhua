"""
ARCHIVO: blackbox_middleware.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. PRINCIPIO DRY (Don't Repeat Yourself): Se centralizó este archivo para 
   eliminar 56 copias redundantes, reduciendo la deuda técnica.
2. CARGA DINÁMICA DE CONFIGURACIÓN: A diferencia de la versión original, 
   esta versión utiliza 'inspect' para rastrear qué bloque está haciendo la 
   llamada. Esto permite que el Middleware viva en 'shared_components' pero 
   lea el 'AppConfig.json' específico de la carpeta del bloque llamador.
3. AISLAMIENTO DE PROCESOS: Implementa un flujo ETL estricto asegurando que 
   cada bloque tenga sus propios directorios temporales de entrada y salida.
-------------------------------------------------------------------------------
"""

from shared_components import Sys
import json
import pandas as pd
import os
from random import randint
import logging
import tempfile
import inspect

# Importación del disparador centralizado
try:
    from shared_components import Trigger
except ImportError:
    from shared_components import Trigger # Fallback para pruebas locales

logging.basicConfig(level=logging.INFO)
LOGER = logging.getLogger()

def get_caller_dir():
    """
    RASTREO DE CONFIGURACIÓN:
    Busca en la pila de ejecución (stack) la ruta del archivo que invocó 
    esta función. Esto es vital para encontrar el AppConfig.json correcto 
    sin importar qué bloque (BuildingBlock) esté activo.
    """
    for frame_info in inspect.stack():
        filename = frame_info.filename
        # Evitamos apuntar a la carpeta de componentes compartidos o internos
        if "shared_components" not in filename and "<" not in filename:
            return os.path.dirname(os.path.abspath(filename)) + "/"
    return os.getcwd() + "/"


def blackbox(data, params, POSTMAN=None):
    """
    ORQUESTADOR BLACKBOX (MIDDLEWARE):
    Gestiona el ciclo de vida de ejecución de un bloque de análisis.

    Configuraciones implementadas:
    - Identificación automática del bloque llamador.
    - Validación de formatos de entrada según AppConfig.json.
    - Creación de rutas BBOX_TEMP, BBOX_OUTPUT y BBOX_ROLLBACK por ejecución.
    """
    
    # --- CONFIGURACIÓN DINÁMICA ---
    # Se localiza la carpeta del bloque actual para leer su ADN (AppConfig.json)
    ACTUAL_PATH = get_caller_dir()
    try:
        with open(ACTUAL_PATH + 'AppConfig.json') as json_file:
            App_configurations = json.load(json_file)
    except FileNotFoundError:
        LOGER.error(f"CONFIGURACIÓN NO ENCONTRADA: Falta AppConfig.json en {ACTUAL_PATH}")
        # Valores de seguridad por defecto
        App_configurations = {"NAME_APPLICATION": "Desconocida", "INPUT_DATA_FORMAT": ["any"]}

    NAME_APPLICATION = App_configurations.get("NAME_APPLICATION", "Desconocida")
    INPUT_DATA_FORMAT = App_configurations.get("INPUT_DATA_FORMAT", ["any"])

    ###########################################################################
    # FASE 1: EXTRACT (Preparación del Entorno)
    ###########################################################################
    head, tail = os.path.split(data['data'])
    params['BBOX_INPUT_PATH'] = head + "/"      
    params['BBOX_INPUT_NAMEFILE'] = tail        

    # Configuración de carpetas volátiles (temporales)
    params['BBOX_TEMP_PATH'] = tempfile.mkdtemp() + "/"
    params['BBOX_OUTPUT_PATH'] = tempfile.mkdtemp() + "/"
    
    # Gestión de Rollback (Respaldo en caso de error)
    rollback_base_path = ACTUAL_PATH + "rollback/"
    if not os.path.exists(rollback_base_path):
        try:
            os.makedirs(rollback_base_path)
        except Exception:
            pass
    
    params['BBOX_ROLLBACK_PATH'] = tempfile.mkdtemp(dir=rollback_base_path) + "/"

    # Validación de protocolos de entrada
    data_type = data.get('type', 'error')
    if data_type == "error":
        return {'data': '', 'type': '', 'status': 'ERROR', 'message': f"Entrada inválida para {NAME_APPLICATION}"}
        
    if data_type in INPUT_DATA_FORMAT or "any" in INPUT_DATA_FORMAT:
        LOGER.info(f"Protocolo de entrada validado para: {NAME_APPLICATION}")
    else:
        return {'data': '', 'type': '', 'status': 'ERROR', 'message': f"Formato {data_type} no soportado por {NAME_APPLICATION}"}

    ######################################################################
    # FASE 2: TRANSFORM (Ejecución del Algoritmo)
    ######################################################################
    # Se delega la ejecución al Trigger centralizado
    response = Trigger.execute(params, App_configurations, POSTMAN=POSTMAN)
    
    if response.get('status') != 0:
        error_msg = response.get('data', {}).get('message', 'Error desconocido en Trigger')
        return {'data': '', 'type': '', 'status': 'ERROR', 'message': f"Fallo en ejecución ({NAME_APPLICATION}): {error_msg}"}
        
    response = response['data']

    ######################################################################
    # FASE 3: LOAD (Control de Calidad de Salida)
    ######################################################################
    # Verificación de integridad del archivo generado
    if not os.path.isfile(response.get('data', '')):
        LOGER.error(f"ERROR DE SALIDA: No se generó el archivo de resultados en {NAME_APPLICATION}")
        return {'data': '', 'type': '', 'status': "ERROR", "message": "Archivo de salida no encontrado"}

    # Verificación de contenido (evitar archivos vacíos)
    if os.stat(response['data']).st_size == 0:
        LOGER.error(f"ERROR DE CONTENIDO: El archivo generado por {NAME_APPLICATION} está vacío")
        return {'data': '', 'type': '', 'status': "ERROR", "message": "Archivo de salida sin datos"}

    return response