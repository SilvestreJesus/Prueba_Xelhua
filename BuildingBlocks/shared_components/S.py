"""
ARCHIVO: S.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. SERVIDOR DE RECEPCIÓN (WORKER NODE DAEMON): Este script es el receptor 
   universal del nodo. Mantiene un socket TCP abierto esperando paquetes 
   de trabajo de la red.
2. PROCESAMIENTO ASÍNCRONO: Al recibir un dataset, no bloquea el hilo principal. 
   Delega la ejecución real (ETL) a un proceso secundario (ClientProcess) 
   utilizando 'multiprocessing', permitiendo que el nodo reciba más trabajos 
   simultáneamente.
3. INTEGRACIÓN CORE: Actúa como el puente que conecta la red (Sockets) 
   con la lógica de negocio (building_middleware).
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
import multiprocessing as mp
import gc
import shutil

# --- Importaciones Centralizadas del Core ---
from shared_components import C
from shared_components import building_middleware as BB
from shared_components import BB_dispatcher 
try:
     from shared_components import ClientPattern 
except ImportError:
    pass # Se resolverá cuando se centralice ClientPattern.py

# --- Importaciones Pendientes de Centralizar ---
from shared_components.Postman import postman
from shared_components.ThreadCreator import threadMonitor

# Archivo de registro de soluciones
SOLUTIONS_FILE = "records.txt"
with open(SOLUTIONS_FILE, 'a+') as f_records:
    pass

THREADS_LIST = {}

def ClientProcess(metadata, data_acq_time):
    """
    Subproceso que maneja la lógica de ejecución una vez que los datos 
    han sido descargados completamente por el servidor.
    """
    TIME_ACQUISITION = data_acq_time
    TIME_SERVICE = time.time()
    TIME_TRANSFORM = 0
    TIME_EXECUTION = 0

    DAG = metadata['DAG']
    data = metadata['data']
    auth = metadata['auth']

    AG = postman(GATEWAYS_LIST, SERVICE_NAME, SERVICE_IP, SERVICE_PORT, NETWORK, TPSHOST, API_GATEWAY=API_GATEWAY, LOGER=LOGER, tokenuser=auth['user'])
    os.chdir(BASE_PATH)
    
    service_name = DAG['service']
    params = DAG.get('params', {})
    children = DAG.get('children', [])
    ENV_VARS = metadata.get('ENV', {})

    id_service = DAG['id']
    control_number = DAG['control_number']

    apply_pattern = False
    if 'pattern' in DAG:
        pattern = DAG['pattern']
        apply_pattern = pattern.get('active', False)

    AG.Set_IdService(id_service)
    AG.Set_RN(control_number)
    AG.start()
    
    data = AG.ValidateDataMap(data, auth)

    index_opt = True 
    if 'SAVE_DATA' in params:        
        index_opt = params['SAVE_DATA']
    else:
        for key in params:
            if isinstance(params[key], dict) and 'SAVE_DATA' in params[key]:
                index_opt = params[key]['SAVE_DATA']
                break

    LOGER.info("====== INDEXING RESULTS : %s" % index_opt)

    if 'actions' in DAG:
        if isinstance(DAG['actions'], list):
            actions = DAG['actions']
        else:
            actions = [DAG['actions']] 
            service_name = service_name + "_" + str(DAG['actions'][0])
    else:
        actions = ['REQUEST']
        params = {'REQUEST': params}

    LOGER.info("Starting execution process... %s" % id_service)

    # --- FASE DE TRANSFORMACIÓN (Ejecución del Middleware) ---
    TIME_TRANSFORM = time.time()
    if apply_pattern:
        LOGER.info("...### Creating Pattern to ###... %s" % id_service)
        CP = ClientPattern.client_pattern(control_number, id_service, LOGER=LOGER, POSTMAN=AG, Monitor_Threads=TH_MONITOR)
        result = CP.run_pattern(pattern, data, auth, DAG)
        result["metadata"] = {"product_name": "list of products by level"}
    else:
        result = BB.middleware(data, actions, params, LOGER=LOGER, ENV=ENV_VARS, POSTMAN=AG)
        if 'EXECUTION_TIME' in result:
            TIME_EXECUTION = result['EXECUTION_TIME']
            del result['EXECUTION_TIME']

    del data
    if "metadata" not in result:
        result['metadata'] = {}

    TIME_TRANSFORM = time.time() - TIME_TRANSFORM
    LOGER.info("Finishing execution process... %s" % service_name)

    # --- FASE DE INDEXACIÓN ---
    if index_opt and result.get('status') != "ERROR":
        label = AG.ArchiveData(result['data'], result['data'].split("/")[-1], metadata=result['metadata'])
    else:
        label = False
        LOGER.error(result.get('message', 'Unknown Error'))
        LOGER.info("Skipping index process")
    
    with open(SOLUTIONS_FILE, 'a+') as f_records:
        f_records.write("%s\t%s\t%s\t%s\n" % (id_service, control_number, result['data'], json.dumps(children)))

    # --- FINALIZAR Y REPORTAR ---
    ToSend = AG.CreateMessage(control_number, result.get('message', ''), result.get('status', 'ERROR'), label=label, type_data=result.get('type', ''), index_opt=index_opt, include_hash=True)
    AG.terminate(result.get('status', 'ERROR'), ToSend)

    # --- DESPACHAR A LOS NODOS HIJOS ---
    LOGER.info("Sending to children...")
    dispatcher = BB_dispatcher.bb_dispatcher(control_number, id_service, NETWORK, LOGER=LOGER, POSTMAN=AG, Tolerant_errors=Tolerant_errors)
    
    try:
        for child in children:
            if result.get('status') == "ERROR":
                result['type'] = "error"
                f = tempfile.NamedTemporaryFile(suffix=".error", delete=False)
                f.write(b"Error")
                fname = f.name
                result['data'] = fname
                f.close()
                f = open(fname, "rb")
            else:
                f = open(result['data'], "rb")

            dispatcher.Send_to_BB(result, f, auth, child, ENV=ENV_VARS)
    except KeyError:
        LOGER.error("ERROR: missing children attributes")

    # --- LIMPIEZA DE MEMORIA ---
    shutil.rmtree(result.get('data', ''), ignore_errors=True) 
    del result
    
    TIME_SERVICE = time.time() - TIME_SERVICE
    AG.Set_Time("serv", TIME_SERVICE)
    acq = AG.Get_Times("acq")
    AG.Set_Time("acq", acq + TIME_ACQUISITION)
    AG.Set_Time("trans", TIME_TRANSFORM)
    AG.Set_Time("exec", TIME_EXECUTION)
    AG.ReportTimes()
    AG.join()
    
    gc.collect()
    return True

# =============================================================================
# INICIALIZACIÓN DEL SERVIDOR TCP
# =============================================================================

if __name__ == "__main__":
    BASE_PATH = os.getcwd()
    logging.basicConfig(level=logging.INFO)
    LOGER = logging.getLogger()
    
    GATEWAYS_LIST = os.getenv("API_GATEWAY", "").split(",")
    NETWORK = os.getenv("NETWORK")
    SERVICE_NAME = os.getenv("SERVICE_NAME")
    SERVICE_IP = os.getenv("HOSTNAME") 
    SERVICE_PORT = os.getenv("SERVICE_PORT") 
    TPSHOST = os.getenv("TPS_MANAGER") 

    Tolerant_errors = 10 
    TEMP_AG = postman(GATEWAYS_LIST, SERVICE_NAME, SERVICE_IP, SERVICE_PORT, NETWORK, TPSHOST, LOGER=LOGER)

    TH_MONITOR = threadMonitor(LOGER=LOGER)
    TH_MONITOR.start()

    Gtwy = TEMP_AG.Select_gateway()
    if Gtwy == 1:
        LOGER.error("BAD GATEWAY")
        time.sleep(2)
        sys.exit(1)
    else:
        API_GATEWAY = Gtwy

    HEADERSIZE = 4096
    port = 80
    BUFF_SIZE = 81920 * 10
    SEPARATOR = "<SEPARATOR>"

    serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serv.bind((socket.gethostname(), port))
    host_name = socket.gethostname() 
    host_ip = socket.gethostbyname(host_name) 
    LOGER.info(f"SERVER ON! IP: {host_ip} PORT: {port}\n\n")
    
    TEMP_AG.init_service()
    serv.listen(Tolerant_errors)

    while True:
        conn, addr = serv.accept()
        data_acq_time = time.time()
        LOGER.info(f"CONNECTION FROM: {addr[0]} PORT: {addr[1]}\n")

        # 1. Recibir Cabecera
        data_to_recv = HEADERSIZE
        reciv_amount = 0
        from_client = []
        while True:
            msg = conn.recv(data_to_recv)
            reciv_amount = len(msg)
            from_client.append(msg)
            if reciv_amount == data_to_recv:
                msg_size, filesize = b"".join(from_client).decode().split(SEPARATOR)
                msglen = int(msg_size)
                filesize = int(filesize)
                break
            else:
                data_to_recv -= reciv_amount

        # 2. Recibir Metadatos
        data_to_recv = msglen
        reciv_amount = 0
        from_client = []
        while True:
            msg = conn.recv(data_to_recv)
            reciv_amount = len(msg)
            from_client.append(msg)
            if reciv_amount == data_to_recv:
                metadata_raw = pickle.loads(b"".join(from_client)) 
                break
            else:
                data_to_recv -= reciv_amount

        metadata = json.loads(metadata_raw) 
        file_ext = metadata['data']['type'] 

        # 3. Recibir Archivo (Chunks)
        INPUT_TEMP_FILE = tempfile.NamedTemporaryFile(delete=False, suffix="." + file_ext) 
        reciv_amount = 0
        
        while True:
            bytes_read = conn.recv(BUFF_SIZE)
            reciv_amount += len(bytes_read)
            INPUT_TEMP_FILE.write(bytes_read)
            if reciv_amount >= filesize: 
                break

        inputfile_name = INPUT_TEMP_FILE.name
        INPUT_TEMP_FILE.close()

        # Enviar confirmación (Acknowledge)
        result = json.dumps({'status': 'OK'})
        result = pickle.dumps(result)
        result = bytes(f'{len(result):<{HEADERSIZE}}', 'utf-8') + result
        conn.sendall(result)    

        data_acq_time = time.time() - data_acq_time
        
        # 4. Lanzar el proceso en segundo plano
        if metadata['data']['type'] == "SOLUTION":
            os.remove(inputfile_name)
        else:
            metadata['data']['data'] = inputfile_name
            
        try:
            thread1 = mp.Process(target=ClientProcess, args=(metadata, data_acq_time))
            thread1.start()
            TH_MONITOR.AppendThread(thread1)
        except Exception as e:
            LOGER.error(f"Fallo al lanzar el subproceso: {e}")

        conn.close()