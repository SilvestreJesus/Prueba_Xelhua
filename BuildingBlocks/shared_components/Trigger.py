"""
ARCHIVO: Trigger.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. MOTOR DE EJECUCIÓN CENTRAL: Este script es el núcleo de procesamiento. 
   Se centralizó para estandarizar cómo se lanzan los subprocesos y cómo 
   se manejan los errores de ejecución en los 56 bloques.
2. DIRECTORIO DE TRABAJO DINÁMICO (CWD): Al igual que el middleware, utiliza 
   inspección de pila para asegurar que los comandos se ejecuten en la carpeta 
   del bloque original, no dentro de 'shared_components'.
3. GESTIÓN DE BASURA (GARBAGE COLLECTION): Asegura la limpieza estricta de 
   carpetas temporales (SOURCE y SINK) para evitar fugas de memoria en el servidor.
-------------------------------------------------------------------------------
"""

from shared_components import Sys
import json
import pandas as pd
import os
from random import randint
import logging
import importlib
from shared_components import Shutil
import tempfile
import time
from shared_components import Subprocess
import multiprocessing as mp
import inspect

# Importaciones centralizadas
from shared_components import utils
try:
    from shared_components  import CustomScript
except ImportError:
    from shared_components import CustomScript

logging.basicConfig(level=logging.INFO)
LOGER = logging.getLogger()

def get_caller_dir():
    """
    RASTREO DE DIRECTORIO BASE:
    Encuentra la carpeta original del bloque que invocó el proceso.
    Garantiza que el Current Working Directory (CWD) apunte a los scripts locales.
    """
    for frame_info in inspect.stack():
        filename = frame_info.filename
        if "shared_components" not in filename and "<" not in filename:
            return os.path.dirname(os.path.abspath(filename)) + "/"
    return os.getcwd() + "/"


def call_app(comando, POSTMAN=None):
    """
    Lanza un subproceso en el sistema operativo para ejecutar un comando externo 
    (ej. un script de R o de Python) y captura su salida en tiempo real.

    Args:
        comando (str): El comando exacto a ejecutar en la terminal.
        POSTMAN (object, optional): Objeto para enviar logs al sistema de mensajería.

    Returns:
        int: Código de estado de la ejecución (0 es éxito, cualquier otro es error).
    """
    sp = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, close_fds=True)
    LOGER.debug("==== PID ====== %s" % sp.pid)
    decoded_log = ""
    
    while True:
        linea = sp.stdout.readline()
        if not linea:
            break
        linea_decodificada = linea.decode().rstrip()
        LOGER.info("stdout: %s" % linea_decodificada)
        decoded_log += linea_decodificada + "\n"

    sp.wait()
    sp.terminate()

    if POSTMAN is not None:
        data = POSTMAN.CreateMessage(None, decoded_log, "LOG")
        POSTMAN.WarnGateway(data)
        
    return sp.returncode


def execute(params, AppConfig, POSTMAN=None):
    """
    MOTOR DE EJECUCIÓN PRINCIPAL:
    Lee la configuración del bloque y orquesta las fases de EXTRACCIÓN, 
    TRANSFORMACIÓN (ejecución) y CARGA.

    Args:
        params (dict): Parámetros de entorno y rutas temporales creadas por el middleware.
        AppConfig (dict): Configuración leída del AppConfig.json del bloque.
        POSTMAN (object, optional): Gestor de mensajería.

    Returns:
        dict: Estructura con el estado final y los metadatos de los resultados.
    """
    ACTUAL_PATH = get_caller_dir()
    
    RESERVED_PARAMS = {
        "SOURCE": params['BBOX_INPUT_PATH'] + params['BBOX_INPUT_NAMEFILE'],
        "SOURCE_PATH": params['BBOX_INPUT_PATH'],
        "SOURCE_FILENAME": params['BBOX_INPUT_NAMEFILE'],
        "SINK": params['BBOX_OUTPUT_PATH'],
        "CWD": ACTUAL_PATH
    }

    Extract_config = AppConfig.get('EXTRACT', {})
    Transform_config = AppConfig.get('TRANSFORM', {})
    Load_config = AppConfig.get('LOAD', {})

    # ----------------- FASE: EXTRACT -----------------
    if Extract_config.get('COMPRESS', False):
        utils.UncompressFile(RESERVED_PARAMS['SOURCE'], params['BBOX_TEMP_PATH'])
        RESERVED_PARAMS['SOURCE'] = params['BBOX_TEMP_PATH'] 

    # Configuración del entorno de la aplicación a través de CustomScript
    CustomScript.config_env()
    RESERVED_PARAMS['ENV_DATASET'] = utils.Get_Env_FromFile(RESERVED_PARAMS['SOURCE'])
    LOGER.info("ENV DATASET: %s" % (RESERVED_PARAMS['ENV_DATASET']))

    execution_status = 1
    try:
        app_message = "OK"
        EXECUTION_TIME = time.time()
        
        # ----------------- FASE: TRANSFORM -----------------
        if Transform_config.get('CUSTOM_APP', False):
            try:
                CustomScript.custom_app(params, RESERVED_PARAMS)
                execution_status = 0
            except Exception as e:
                exception_type, exception_object, exception_traceback = sys.exc_info()
                filename_error = exception_traceback.tb_frame.f_code.co_filename
                line_number = exception_traceback.tb_lineno
                LOGER.error("CUSTOMAPP ERROR: %s, line: %s in %s" % (str(e), line_number, filename_error))
                execution_status = 1
        else:
            command = Transform_config.get('COMMAND', '')
            command = utils.FormatCommand(command, params, reserved_params=RESERVED_PARAMS, POSTMAN=POSTMAN)
            LOGER.info("==== EXECUTING COMMAND ====== %s" % command)
            execution_status = call_app(command, POSTMAN=POSTMAN)
            LOGER.info("status code: %s" % execution_status)

        EXECUTION_TIME = time.time() - EXECUTION_TIME

        if execution_status != 0:
            app_message = "Internal error in the application"

        # ----------------- FASE: LOAD -----------------
        if Load_config.get('OUTPUT_NAMEFILE', "") != "":
            list_namefiles = Load_config['OUTPUT_NAMEFILE']
            if not isinstance(list_namefiles, list):
                list_namefiles = list_namefiles.split(",")

            for tmp_name in list_namefiles: 
                try:
                    namefile = utils.FormatCommand(tmp_name, params, reserved_params=RESERVED_PARAMS, POSTMAN=POSTMAN)
                    if len(namefile.split("/")) >= 2: 
                        result = namefile
                        Load_config['COMPRESS'] = True
                    else:
                        result = RESERVED_PARAMS['SINK'] + namefile 
                        
                    result = shutil.move(result, params['BBOX_ROLLBACK_PATH']) 
                    break
                except Exception:
                    LOGER.debug("-- NOT THIS ONE:%s" % tmp_name)
                    pass

        if Load_config.get('COMPRESS', False):
            result = utils.CompressFile(params['BBOX_ROLLBACK_PATH'], RESERVED_PARAMS['SINK'], ignore_list=Load_config.get('ignore_list', []))

        # --- LIMPIEZA (GARBAGE COLLECTION) ---
        try:
            os.remove(params['BBOX_INPUT_PATH'] + params['BBOX_INPUT_NAMEFILE'])
        except FileNotFoundError:
            pass
        shutil.rmtree(params['BBOX_TEMP_PATH'], ignore_errors=True) 
        shutil.rmtree(params['BBOX_OUTPUT_PATH'], ignore_errors=True)
        
        # --- METADATOS FINALES ---
        if 'result' not in locals():
            result = "error_path"
            ext = "none"
        else:
            try:
                name, ext = result.split(".")
            except ValueError:
                ext = "folder"

        LOGER.info("results are in %s" % result)

        metadata = {"product_name": AppConfig.get("NAME_APPLICATION", "App")}
        if "METADATA" in AppConfig:
            meta = AppConfig["METADATA"]
            if 'key' in meta:
                metadata['product_name'] = utils.FormatCommand(meta['key'], params, reserved_params=RESERVED_PARAMS, POSTMAN=POSTMAN)
                if 'list' in meta:
                    metadata['product_name'] = meta["list"].get(metadata['product_name'], metadata['product_name'])

        response = {
            "data": result, 
            "type": ext, 
            "status": "OK", 
            "message": app_message, 
            "EXECUTION_TIME": EXECUTION_TIME, 
            "metadata": metadata
        }

    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        filename_error = exception_traceback.tb_frame.f_code.co_filename
        line_number = exception_traceback.tb_lineno
        LOGER.error("BLACKBOX ERROR: %s, line: %s in %s" % (str(e), line_number, filename_error))
        response = {"data": "", "type": "", "status": "ERROR", "message": str(e)}
        return {'status': 1, 'data': response}

    return {'status': execution_status, 'data': response}