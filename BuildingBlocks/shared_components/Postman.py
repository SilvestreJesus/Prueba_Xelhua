"""
ARCHIVO: Postman.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. GESTOR DE COMUNICACIÓN HTTP (API GATEWAY): Esta clase actúa como un hilo 
   (Thread) en segundo plano que maneja todas las peticiones RESTful entre 
   los bloques de ejecución y el coordinador central (API Gateway).
2. HEARTBEAT PATTERN (HealthCheck): Mantiene viva la conexión informando al 
   coordinador que el nodo sigue operando, evitando que la tarea sea reasignada.
3. CENTRALIZACIÓN: Se consolidó para evitar que cambios en las rutas del 
   API Gateway obligaran a refactorizar 22 aplicaciones distintas.
-------------------------------------------------------------------------------
"""

from threading import Thread
import time
import requests as api
import logging
import json
import tempfile
import multiprocessing as mp
import os
import hashlib
import magic as M
import pandas as pd

# --- Importaciones Centralizadas del Core ---
try:
    from shared_components import functions as utils_func
except ImportError:
    pass

# --- Manejo de Almacenamiento Remoto (Mictlan) ---
try:
    from shared_components.mictlanx_client import mictlanx_client
except ImportError:
    pass # Solo se usa si STORAGE_OPT es MICTLAN

# (Asumiendo que Shutil y Cgi son wrappers locales, usamos las librerías estándar por seguridad)
import shutil
import cgi

class postman(Thread):
    """
    Hilo de comunicación principal. Administra métricas de tiempo, monitoreo 
    de sub-tareas, registro de productos y comunicación de estado con el Gateway.
    """

    def __init__(self, GATEWAYS_LIST, SERVICE, SERVICE_IP, SERVICE_PORT, NETWORK, TPSHOST, API_GATEWAY=None, LOGER=None, tokenuser=None):
        Thread.__init__(self)
        if LOGER is None:
            self.LOGER = logging.getLogger()
        else:
            self.LOGER = LOGER

        self.API_GATEWAY = API_GATEWAY
        self.GATEWAYS_LIST = GATEWAYS_LIST
        self.SERVICE = SERVICE
        self.SERVICE_IP = SERVICE_IP
        self.SERVICE_PORT = SERVICE_PORT
        self.CONTEXT = NETWORK
        self.TPSHOST = TPSHOST
        self.API_KEY = os.getenv("API_KEY", "")
        self.TOKENUSER = tokenuser
        
        # Configuración de Almacenamiento Remoto
        self.REMOTE_STORAGE = os.getenv("STORAGE_OPT", "LOCAL")
        if self.REMOTE_STORAGE == "MICTLAN":
            try:
                self.STORAGE_CLIENT = mictlanx_client(NETWORK, self.LOGER)
            except NameError:
                self.LOGER.error("Mictlan client no importado correctamente.")

        # Variables de Estado
        self.status = "STANDBY"
        self.RN = None
        self.id_service = None
        self.last_message = {}
        self._running = True
        self.hash_product = ""
        self.times = {
            "id": "", "acq": 0, "serv": 0, "trans": 0, 
            "exec": 0, "idx": 0, "comm": 0
        } 

    def init_service(self):
        """Registra el nodo activo en el API Gateway."""
        try:
            if self.SERVICE is not None and self.SERVICE_IP is not None and self.SERVICE_PORT is not None:
                ToSend = json.dumps({"SERVICE": self.SERVICE, "ID": self.SERVICE_IP, "IP": self.SERVICE_IP, "PORT": int(self.SERVICE_PORT), "CONTEXT": self.CONTEXT})
                url = f'http://{self.API_GATEWAY}/ADD'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}

                res = api.post(url, data=ToSend, headers=headers).json()
                self.LOGER.debug("INIT SERVICE SUCCESS")
            else:
                self.LOGER.error("NOT ENOUGH INFO TO INIT")
        except Exception as e:
            self.LOGER.error(f"ERROR INIT SERVICE: {e}, BAD PARAMETERS")
            sys.exit(1)

    def Select_gateway(self):
        """Busca el primer Gateway disponible y saludable en la red."""
        for ag in self.GATEWAYS_LIST:
            try:
                url = f'http://{ag}/health'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
                res = api.get(url, headers=headers).json()
                if res.get('status') == "OK":
                    self.API_GATEWAY = ag
                    return ag   
            except Exception:
                pass
        self.API_GATEWAY = None
        return 1

    def MonitorService(self, token_project, token_solution):
        """Consulta el estado general de una solución en el Gateway."""
        try:
            t = time.time()
            url = f"http://{self.API_GATEWAY}/monitor/v2/{token_project}/{token_solution}"
            headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
            res = api.get(url, headers=headers).json()
            self.times['comm'] += time.time() - t
            if res.get('status') == "OK":
                return res
            return None
        except Exception:
            return None

    def MonitorSpecificService(self, token_project, token_solution, list_task, kind="task_list"):
        """Consulta el estado de tareas específicas (Sub-DAGs)."""
        try:
            t = time.time()
            ToSend = json.dumps({"tasks": list_task, "kind_task": kind})
            url = f"http://{self.API_GATEWAY}/monitor/v2/{token_project}/{token_solution}"
            headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
            res = api.post(url, data=ToSend, headers=headers).json()
            self.times['comm'] += time.time() - t
            if res.get('status') == "OK":
                return res
            return None
        except Exception as e:
            self.LOGER.error(f"BAD REQUEST AT MONITORING: {e}")
            return None
        
    def ValidateSubtask(self, token_solution, task_list):
        """Verifica si ciertas subtareas ya fueron procesadas previamente."""
        try:
            t = time.time()
            ToSend = json.dumps({"token_solution": token_solution, "task_list": task_list})
            url = f"http://{self.API_GATEWAY}/Validate_subtask_executions"
            headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
            res = api.post(url, data=ToSend, headers=headers).json()
            self.times['comm'] += time.time() - t
            if res.get('status') == "OK":
                return res
            return None
        except Exception:
            return None

    def VisualProducts_Map_Manager(self, action, token_solution, token_dispatcher='', token_producer='', data_obj='', levels=[]):
        """Gestiona el grafo visual de productos resultantes en el Gateway."""
        ToSend = json.dumps({
            "action": action, "token_solution": token_solution,
            "token_dispatcher": token_dispatcher, "token_producer": token_producer,
            "data_obj": data_obj, "levels": levels
        })
        t = time.time()
        while True:
            try:
                url = f'http://{self.API_GATEWAY}/ProductsObjectMap'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
                res = api.post(url, data=ToSend, headers=headers).json()
                self.times['comm'] += time.time() - t
                return res
            except Exception:
                self.Select_gateway()
                if self.API_GATEWAY is None:
                    return {"status": "ERROR", "info": "ERROR"}

    def GetResults(self, token_solution, task, auth):
        """Descarga archivos de resultados desde otros nodos a través del Gateway."""
        t = time.time()
        while True:
            kind = "subtask_list"
            res_monitor = self.MonitorSpecificService(auth['user'], token_solution, [task], kind=kind)

            file_is_ready = False
            if res_monitor and task in res_monitor.get('list_task', {}): 
                task_info = res_monitor["list_task"][task]
                if task_info['status'] in ["OK", "FINISHED"]:                
                    file_is_ready = True
                elif task_info['status'] in ["ERROR", "FAILED"]:
                    ext = "error"
                    file_group = tempfile.NamedTemporaryFile(delete=False, suffix="." + ext) 
                    fname = file_group.name
                    file_group.close()
                    break
                else:
                    self.LOGER.error("Datos no listos aún.")
            else:
                self.LOGER.error(f"Tarea no encontrada en lista {kind}")

            if file_is_ready:
                ToSend = {
                    "data": {"token_user": auth['user'], "token_solution": token_solution, "task": task, "catalog": auth['workspace']},
                    "type": "SOLUTION"
                }
                url = f'http://{self.API_GATEWAY}/getfile'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
                response = api.post(url, json=ToSend, headers=headers, stream=True)

                try:
                    params = cgi.parse_header(response.headers.get('Content-Disposition', ''))[-1]
                    ext = params.get('filename', 'file.tmp').split(".")[-1]

                    file_group = tempfile.NamedTemporaryFile(delete=False, suffix="." + ext) 
                    fname = file_group.name
                    file_group.close()
                    
                    with open(fname, 'wb') as target:
                        response.raw.decode_content = True
                        shutil.copyfileobj(response.raw, target)
                    break
                except Exception as ke:
                    self.LOGER.error(f"Error al descargar datos: {ke}")
            else:
                time.sleep(5) 
            
        self.times['acq'] += time.time() - t
        return {"data": fname, "type": ext}

    def ReportTimes(self):
        """Envía las métricas de rendimiento (profiling) al Gateway."""
        ToSend = json.dumps({"token_solution": self.RN, "times": self.times})
        while True:
            try:
                url = f'http://{self.API_GATEWAY}/report_time'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
                res = api.post(url, data=ToSend, headers=headers).json()
                return res
            except Exception:
                self.Select_gateway()
                if self.API_GATEWAY is None:
                    return {"status": "ERROR", "info": "ERROR"}

    def WarnGateway(self, ToSend):
        """Reporta un evento o estado al Gateway (ej. Cambio de estado a ERROR)."""
        task = ToSend.get('task', 'Unknown')
        ToSend = json.dumps(ToSend)
        t = time.time()
        while True:
            try:
                url = f'http://{self.API_GATEWAY}/WARN'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
                res = api.post(url, data=ToSend, headers=headers).json()
                if res.get('status') == "ERROR": 
                    self.LOGER.error(f"Record of {task} FAILED. trying again...")
                else:
                    self.times['comm'] += time.time() - t
                    return res
            except Exception:
                self.Select_gateway()
                if self.API_GATEWAY is None:
                    return {"status": "ERROR", "info": "ERROR"}

    def AskGateway(self, ToSend):
        """Solicita permisos o asignación de recursos al Gateway."""
        ToSend = json.dumps(ToSend)
        while True:
            try:
                t = time.time()
                url = f'http://{self.API_GATEWAY}/ASK'
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
                res = api.post(url, data=ToSend, headers=headers).json()
                self.times['comm'] += time.time() - t
                return res
            except Exception:
                self.Select_gateway()
                if self.API_GATEWAY is None:
                    return {"status": "ERROR", "info": "ERROR"}

    def HealthCheck(self): 
        """Bucle infinito que reporta que el servicio sigue vivo y operando."""
        time_interval = 10
        while self._running:
            ToSend = {'status': "RUNNING", "message": "Health check", "label": '', "task": self.id_service, "type": '', "index": '', "control_number": self.RN}
            self.WarnGateway(ToSend)
            self.LOGER.info(f"================ HEALTHCHECK COMPLETE =================== {self._running}")
            time.sleep(time_interval)
        return True

    def ArchiveData(self, data_path, namefile, id_service=None, mining_statistics=False, metadata={}):
        """Almacena el resultado final en el sistema de almacenamiento designado."""
        if id_service is None:
            id_service = self.id_service
        
        t = time.time()
        self.LOGER.info(f"Saving {id_service}")
        self.calculate_sha256sum(data_path)
        self.LOGER.info(f"Hash resultant product: {self.hash_product}")

        if self.REMOTE_STORAGE != "LOCAL": 
            self.LOGER.info("ALMACENANDO DATOS EN MICTLAN")
            metadata['content_type'] = M.from_file(data_path, mime=True)
            token_data = id_service 
            
            try:
                ext = data_path.split(".")[-1]
            except IndexError:
                ext = ""

            if ext == "csv": 
                dataset = pd.read_csv(data_path)
                metadata['info'] = {'files_info': {}, 'list_of_files': []}
                # Asume que DatasetDescription está en functions.py si se migró correctamente
                try:
                    metadata['info']['files_info'][namefile] = utils_func.DatasetDescription(dataset)
                except Exception:
                    pass
                metadata['info']['list_of_files'].append(namefile)

            headers = {'x-access-token': self.API_KEY}
            cookies = {"metadata": json.dumps(metadata)}
            url = f'http://{self.API_GATEWAY}/metadata/insert/{self.RN}/{id_service}'
            
            try:
                res = api.post(url, headers=headers, cookies=cookies).json()
                self.LOGER.info("Producto Registrado en Metadata")
                if hasattr(self, 'STORAGE_CLIENT'):
                    res = self.STORAGE_CLIENT.put(token_data, data_path, metadata=metadata)
                    self.LOGER.info("DATOS ALMACENADOS CORRECTAMENTE EN MICTLAN")
            except Exception as e:
                self.LOGER.error(f"Error en almacenamiento remoto: {e}")
                
        else: # LOCAL STORAGE
            try:
                with open(data_path, "rb") as file_pointer:
                    headers = {'x-access-token': self.API_KEY}
                    cookies = {}
                    if mining_statistics:
                        cookies = {'x-mining-statistics': "True"}
                    cookies["metadata"] = json.dumps(metadata)

                    url = f'http://{self.API_GATEWAY}/ArchiveData/{self.RN}/{id_service}'
                    res = api.post(url, files={"file": (namefile, file_pointer)}, headers=headers, cookies=cookies).json()
                    
            except Exception as ex:
                self.LOGER.error(f"Error en almacenamiento local: {ex}")
                self.times['idx'] += time.time() - t
                return {"status": "ERROR", "info": "ERROR"}
                
        self.times['idx'] += time.time() - t
        return res

    def run(self):
        """Punto de entrada del hilo (Thread). Inicia el HealthCheck."""
        self.status = "RUNNING"
        self.HealthCheck()
        return True

    def terminate(self, final_status, last_message):
        """Detiene el hilo y envía un mensaje final al Gateway."""
        self.status = final_status
        self._running = False
        self.LOGER.warning(f"SENDING A LAST MESSAGE: {last_message}")
        self.WarnGateway(last_message)

    def calculate_sha256sum(self, filename):
        """Calcula el hash criptográfico del archivo para verificar integridad."""
        h = hashlib.sha256()
        b = bytearray(128 * 1024)
        mv = memoryview(b)
        with open(filename, 'rb', buffering=0) as f:
            while True:
                n = f.readinto(mv)
                if not n:
                    break
                h.update(mv[:n])
        self.hash_product = h.hexdigest()

    def Set_IdService(self, id_service):
        self.id_service = id_service
        self.times['id'] = id_service
        
    def Set_RN(self, RN):
        self.RN = RN

    def Get_Times(self, key=None):
        if key is None:
            return self.times
        return self.times.get(key, 0)
    
    def GetReference(self, query, ENV=None):
        if ENV is None:
            ENV = {}
        try:
            ToSend = json.dumps({"query": query, "ENV": ENV})
            url = f"http://{self.API_GATEWAY}/reference/get"
            headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'x-access-token': self.API_KEY}
            res = api.post(url, data=ToSend, headers=headers).json()
            
            if res.get('status') == "OK":
                return res.get("value")
            return None
        except Exception as e:
            self.LOGER.error(f"EXCEPTION IN GetReference: {e}")
            return None

    def Set_Time(self, time_key, value, operation="replace"):
        if operation == "replace":
            self.times[time_key] = value

    def ValidateDataMap(self, data_map, auth):
        """Verifica y adquiere datos si vienen en formato 'SOLUTION'."""
        dtype = data_map.get('type')

        if dtype == "SOLUTION": 
            task = data_map['data']['task']
            token = data_map['data']['token']
            task = task.replace(".SOLUTION", "") 
            data_map = self.GetResults(token, task, auth)
            
            self.calculate_sha256sum(data_map['data'])
            ToSend = self.CreateMessage(self.RN, "indexing input data hash", "UPDATE", type_data=data_map['type'], include_hash=True)
            self.WarnGateway(ToSend)
            
        return data_map
    
    def CreateMessage(self, RN=None, message='', status='OK', id_service=None, type_data='', parent='', label='', index_opt='', times=None, dag=None, include_hash=False):
        """Estructura un paquete de mensaje JSON estandarizado para el Gateway."""
        id_service = id_service if id_service is not None else self.id_service
        RN = RN if RN is not None else self.RN

        ToSend = {
            'control_number': RN, "task": id_service, 'status': status,
            "message": message, "parent": parent, "label": label,
            "type": type_data, "index": index_opt, "token_user": self.TOKENUSER
        }

        if times is not None:
            ToSend['times'] = times
        if dag is not None:
            ToSend['dag'] = dag
        if include_hash:
            ToSend['hash_product'] = self.hash_product

        return ToSend