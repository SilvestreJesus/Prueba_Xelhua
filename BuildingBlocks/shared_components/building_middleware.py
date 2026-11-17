"""
ARCHIVO: building_middleware.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. ORQUESTADOR DE NODO (HIGH-LEVEL MIDDLEWARE): Este script gestiona la 
   ejecución secuencial de múltiples bloques (apps) dentro de un mismo nodo.
   Se centralizó porque su lógica de ruteo y medición de tiempos es universal.
2. IMPORTACIÓN DINÁMICA CORREGIDA: Ya está configurado para llamar al 
   'blackbox_middleware' desde la nueva ruta 'shared_components', asegurando 
   que la cadena de ejecución no se rompa.
3. REGISTRO DE RENDIMIENTO (PROFILING): Mantiene una bitácora ('Times.txt') 
   para medir cuánto tarda cada bloque. Ideal para futuras optimizaciones de IA.
-------------------------------------------------------------------------------
"""

import sys
import os
import json
import pandas as pd
import importlib
import logging
import time

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

# Configuración de la carpeta de bitácoras (Logs)
logs_folder = "./logs/"
try:
    if not os.path.exists(logs_folder):
        os.makedirs(logs_folder)
except FileExistsError:
    pass

# Escaneo del entorno: Detecta qué bloques (carpetas) están disponibles en este nodo
ignore_list = ['TPS', 'shared_components', 'logs', '__pycache__'] 
list_applications = [name for name in os.listdir(".") if (os.path.isdir(name) and name not in ignore_list)]


def middleware(data, actions, workParams, LOGER=LOG, ENV=None, POSTMAN=None):
    """
    Función orquestadora principal a nivel de Nodo.
    Recibe un paquete de datos y una lista de 'acciones' (bloques a ejecutar),
    y los procesa en cadena, pasando el resultado de uno como entrada del siguiente.

    Args:
        data (dict): Diccionario con el archivo de entrada inicial y su tipo.
        actions (list): Lista de nombres de las aplicaciones (bloques) a ejecutar en orden.
        workParams (dict): Diccionario maestro con los parámetros específicos para cada bloque.
        LOGER (logging.Logger, optional): Instancia del logger activo.
        ENV (dict, optional): Variables de entorno globales.
        POSTMAN (object, optional): Gestor de mensajería para alertas.

    Returns:
        dict: Resultado final después de pasar por todos los bloques especificados en 'actions'.
    """
    if ENV is None:
        ENV = {}
        
    try:
        LOGER.info(list_applications)
        LOGER.info("Running BB middleware")
        C_ST = time.time() # Flag para iniciar el cronómetro global
        
        # Abre (o crea) el archivo para registrar los tiempos de ejecución
        f = open(logs_folder + 'Times.txt', 'a+') 
        
        if len(actions) <= 0:
            LOGER.error("No APPs selected.")
            raise Exception("No APPs selected.")

        # Itera sobre cada bloque solicitado en la cadena de ejecución
        for app in actions:
            app = app.upper() 
            LOGER.info("Looking for %s" % app)
            
            # Verifica que el bloque solicitado realmente exista en este nodo
            if app in list_applications:
                
                # --- INVOCACIÓN DEL MIDDLEWARE DE BAJO NIVEL (BLACKBOX) ---
                LOGER.debug("importing..... shared_components.blackbox_middleware")
                mod = importlib.import_module('shared_components.blackbox_middleware')
                
                params = workParams.get(app, {}) 
                params['ENV'] = ENV
                params['APP_DIR'] = os.path.join(os.getcwd(), app)

                LOGER.info("RUNNING BLACKBOX FOR: %s" % app)
                
                # Ejecuta el bloque. La 'data' resultante se recicla para la siguiente vuelta del ciclo.
                data = mod.blackbox(data, params, POSTMAN=POSTMAN) 
                
                LOGER.info("BLACKBOX FINISHED with status: %s" % data.get('status', 'UNKNOWN'))

                # Registra cuánto tiempo le tomó a este bloque específico terminar
                f.write("%s, %s \n" % (app, (time.time() - C_ST))) 

                if data.get('status') == "ERROR":
                    LOGER.error(">>> ERROR DETECTED <<< \n STOPING BB")
                    f.close()
                    return data
            else:
                LOGER.error("APP %s doesn't exist in BB..." % app)
                raise Exception("App not found in local node")

        LOGER.info("STOPING BB")
        f.write("BB_TOTAL, %s \n-\n" % ((time.time() - C_ST))) 
        f.close() 
        return data 
        
    except Exception as ex: 
        try:
            f.write("BB_FAILED, %s \n-\n" % ((time.time() - C_ST))) 
            f.close() 
        except Exception:
            pass
            
        LOGER.error("Unexpected error in BB middleware. %s" % (ex))
        return {'data': '', 'type': '', 'status': 'ERROR', 'message': 'Unexpected error in BB middleware. %s' % (ex)}