"""
ARCHIVO: BB_dispatcher.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. CENTRALIZACIÓN DE RED: Este archivo gestiona la distribución de tareas 
   (Dispatcher) hacia otros nodos (BuildingBlocks). Se centralizó para 
   unificar la lógica de reintentos (Retry Pattern) y comunicación.
2. TOLERANCIA A FALLOS: Implementa un mecanismo de recuperación. Si un nodo 
   falla al recibir datos, el dispatcher lo reporta como caído ('DOWN') 
   y solicita un nodo alternativo al Gateway antes de abortar.
-------------------------------------------------------------------------------
"""

import logging
import socket
import os
import sys
import pickle
import json
import pandas as pd
import time
import tempfile
import base64

# Asumiendo que C.py también se centralizará
try:
    from shared_components import C
except ImportError:
    from shared_components import C


class bb_dispatcher():
    """
    Clase encargada de orquestar el envío de datos y tareas desde el 
    bloque actual hacia el siguiente bloque en la cadena de procesamiento (DAG).
    """

    def __init__(self, TOKEN_SOLUTION, SERVICE_ID, CONTEXT, LOGER=None, POSTMAN=None, Tolerant_errors=2):
        """
        Inicializa el despachador con los identificadores de la solución y contexto de red.

        Args:
            TOKEN_SOLUTION (str): ID único de la ejecución actual.
            SERVICE_ID (str): ID del bloque/servicio que está instanciando este despachador.
            CONTEXT (dict): Contexto de red (variables de entorno globales).
            LOGER (logging.Logger, optional): Instancia del logger. Si es None, crea uno.
            POSTMAN (object, optional): Gestor de mensajería para comunicarse con el Gateway.
            Tolerant_errors (int, optional): Número de reintentos permitidos antes de marcar un nodo como caído. Por defecto 2.
        """
        if LOGER is None:
            self.LOGER = logging.getLogger()
        else:
            self.LOGER = LOGER

        self.TOKEN_SOLUTION = TOKEN_SOLUTION
        self.PARENT = SERVICE_ID
        self.CONTEXT = CONTEXT
        self.POSTMAN = POSTMAN
        self.Tolerant_errors = Tolerant_errors


    def Send_to_BB(self, data_map, data_pointer, auth, child, ENV=None, parent=None):
        """
        Solicita un nodo disponible al Gateway y envía los datos procesados para que el 
        siguiente bloque continúe el trabajo. Maneja fallos de conexión solicitando nodos de respaldo.

        Args:
            data_map (dict): Metadatos de la información a enviar.
            data_pointer (str): Ruta del archivo físico que contiene los datos a procesar.
            auth (dict): Credenciales de autorización para el servicio REST.
            child (dict): Información del bloque destino (nodo hijo en el DAG).
            ENV (dict, optional): Variables de entorno específicas para el bloque destino.
            parent (str, optional): ID del bloque origen. Si es None, usa el asignado en __init__.
        """
        if ENV is None:
            ENV = {}
        if parent is None:
            parent = self.PARENT

        self.LOGER.info("### INFO: file: %s ..." % data_map.get('type', 'Unknown'))
        child['control_number'] = self.TOKEN_SOLUTION 
        
        ######## FASE 1: ASK (Solicitar Recursos al Gateway) #######
        ToSend = {'service': child['service'], 'context': self.CONTEXT}
        res = self.POSTMAN.AskGateway(ToSend)
        
        if 'info' in res: 
            self.LOGER.error("NO NODES FOUND")
            data = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION, 'no available resources found.', 'ERROR', id_service=child['id'])
            self.POSTMAN.WarnGateway(data)
        else:
            errors_counter = 0
            
            ###### FASE 2: SEND (Enviar Datos al Nodo Asignado) #######
            ip = res['ip']
            port = res['port']
            self.LOGER.debug("Children >>>>>> IP:%s PORT: %s " % (ip, port))
            
            ToSend = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION, 'Starting ejecution.', 'INIT', id_service=child['id'], parent=parent, dag=child, include_hash=True)
            self.POSTMAN.WarnGateway(ToSend)
            
            while True:
                data = C.RestRequest(ip, port, {'data': data_map, 'DAG': child, "auth": auth, "ENV": ENV}, data_file=data_pointer)
                
                if data is not None:
                    self.LOGER.info(">>> DATA SENT SUCCESFULLY <<<")
                    errors_counter = 0
                    break
                else:
                    errors_counter += 1
                    self.LOGER.warning(">>>>>>> NODE FAILED... TRYING AGAIN..%s" % errors_counter)
                    
                    if errors_counter >= self.Tolerant_errors:
                        ######## FASE 3: RECOVERY (Reportar Fallo y Solicitar Nodo Alterno) #######
                        ToSend = {'service': child['service'], 'context': self.CONTEXT, 'update': {'id': res['id'], 'status': 'DOWN'}} 
                        res = self.POSTMAN.AskGateway(ToSend)
                        
                        errors_counter = 0 
                        if 'info' in res: 
                            data = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION, 'no available resources found: %s attempts.' % str(self.Tolerant_errors), 'ERROR', id_service=child['id'])
                            self.POSTMAN.WarnGateway(data)
                            break
                            
                        ip = res['ip']
                        port = res['port']
                        self.LOGER.debug("TRYING A NEW NODE... IP:%s PORT: %s " % (ip, port))