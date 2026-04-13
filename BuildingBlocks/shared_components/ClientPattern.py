"""
ARCHIVO: ClientPattern.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. MOTOR DE PARALELIZACIÓN (MAP-REDUCE): Este script orquesta la división de 
   datasets pesados y su distribución entre múltiples nodos de procesamiento.
2. GESTIÓN DE ESTADO (MONITORING): Implementa bucles de monitoreo asíncrono 
   para rastrear el progreso de los sub-grafos (DAGs) despachados, asegurando 
   que el proceso 'Reduce' solo inicie cuando todos los 'Maps' terminen.
3. CENTRALIZACIÓN: Al unificar este archivo, se estandariza la lógica de 
   fragmentación de datos y manejo de hilos (Threads) en todo el clúster.
-------------------------------------------------------------------------------
"""

import time
import logging
import json
import pandas as pd
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from threading import Thread
import multiprocessing as mp
import os

# --- Importaciones Centralizadas del Core ---
try:
    from shared_components import BB_dispatcher 
except ImportError:
    import BB_dispatcher

# --- Importaciones Pendientes de Centralizar ---
from shared_components import genesis_client as GC
from shared_components.ThreadCreator import threadMonitor

class client_pattern():
    """
    Clase orquestadora para la ejecución de patrones arquitectónicos distribuidos 
    (principalmente Map-Reduce) sobre el clúster Xelhua.
    """

    def __init__(self, TOKEN_SOLUTION, SERVICE_ID, LOGER=None, POSTMAN=None, Monitor_Threads=None):
        if LOGER is None:
            self.LOGER = logging.getLogger()
        else:
            self.LOGER = LOGER

        if Monitor_Threads is None:
            self.TH_MONITOR = threadMonitor()
        else:
            self.TH_MONITOR = Monitor_Threads

        self.TOKEN_SOLUTION = TOKEN_SOLUTION
        self.SERVICE_ID = SERVICE_ID
        self.POSTMAN = POSTMAN
        self.BBOX_OUTPUT_PATH = tempfile.mkdtemp() + "/"

    def CreateDataMap(self, data, id_group):
        """Genera un archivo temporal CSV a partir de un fragmento del DataFrame."""
        file_group = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", prefix=id_group + "-GROUP-") 
        data.to_csv(file_group, index=False)
        fname = file_group.name
        data_map = {"data": fname, "type": "csv"}
        file_group.close()
        return data_map

    def CloneDict(self, dict_obj):
        """Realiza una copia profunda (Deep Copy) de un diccionario usando JSON."""
        return json.loads(json.dumps(dict_obj))

    def GetSubtaskContextVariables(self, id_str):
        """Extrae variables de entorno del string de identificación de la tarea."""
        dict_var_context = {}
        string_context = id_str.replace("-VAL-", "/").replace("-LVL-", "/").replace("-MAP-", "/").replace("-subtask-", "/")
        string_arr = string_context.split("/")
        for var in string_arr:
            key_val = var.split("=")
            if len(key_val) == 2:
                dict_var_context[key_val[0]] = key_val[1]
        return dict_var_context
            
    def Prepare_subdag_instance_v2(self, dag, task, as_original=False):
        """Prepara la instancia del sub-grafo para despachar al nodo hijo."""
        if not as_original: 
            id_group = task.split("-MAP-")[0] 
            dag['id'] = "%s-subtask-%s" % (id_group, dag['id']) 
        return dag

    def Corroborate_pipe_finished(self, dag, list_task):
        """Verifica recursivamente si una tubería (pipeline) y sus hijos han concluido."""
        if dag['id'] in list_task: 
            task_info = list_task[dag['id']]
            if task_info['status'] in ["OK", "FINISHED", "ERROR", "FAILED"]:
                for ch in dag['children']:
                    if not self.Corroborate_pipe_finished(ch, list_task):
                        return False
            else:
                return False
        else:
            return False
        return True

    def list_tasks_in_DAGs(self, list_dags, list_tasks=None):
        """Aplana la jerarquía del DAG para obtener una lista simple de IDs de tareas."""
        if list_tasks is None:
            list_tasks = []
        for dag in list_dags:
            list_tasks.append(dag['id'])
            list_tasks = self.list_tasks_in_DAGs(dag['children'], list_tasks)
        return list_tasks

    def list_tasks_in_DAGs_by_pattern(self, list_dags, task_obj=None):
        if task_obj is None:
            task_obj = {}
        for dag in list_dags:
            if 'pattern' in dag:
                if dag['pattern']['kind'] in ["Chain", "Reduce"] and dag['pattern']['active']:
                    levels_to_process = dag['pattern']['spec']['level_to_process'] 
                    for l in levels_to_process:
                        if l not in task_obj:
                            task_obj[l] = {} 
                        task_obj[l][dag['id']] = {"id": dag["id"], "alias": dag["alias"], "service": dag["service"], "params": dag["params"]}
            
            task_obj = self.list_tasks_in_DAGs_by_pattern(dag['children'], task_obj)
        return task_obj

    def list_tasks_by_pattern(self, dag, levels_to_process):
        task_obj = {}
        for l in levels_to_process:
            if l not in task_obj:
                task_obj[l] = {} 
            task_obj[l][dag['id']] = {"id": dag["id"], "alias": dag["alias"], "service": dag["service"], "params": dag["params"]}
        return task_obj

    def MonitoringByDAG(self, list_of_dags, auth):
        """Bucle de monitoreo que espera hasta que todos los sub-DAGs finalicen."""
        interval = .3
        max_attempts = 150
        att = 0
        list_task = self.list_tasks_in_DAGs(list_of_dags, list_tasks=[])

        while True:
            on_waiting = []
            res_monitor = self.POSTMAN.MonitorSpecificService(auth['user'], self.TOKEN_SOLUTION, list_task, kind="subtask_list")
            att += 1
            
            if res_monitor is not None:
                if res_monitor['status'] == "OK":
                    for dag in list_of_dags:
                        if_finished = self.Corroborate_pipe_finished(dag, res_monitor["list_task"])
                        if not if_finished:
                            on_waiting.append(dag)
                else:
                    self.LOGER.error("El monitor no devolvio nada")

                if len(on_waiting) < len(list_of_dags):
                    break
                if att > max_attempts:
                    self.LOGER.error("Aun estamos esperando las siguientes tareas: %s" % on_waiting)
                    att = 0

            time.sleep(interval)

        return on_waiting

    def Monitoring(self, list_of_task, auth):
        """Bucle de monitoreo simple para una lista plana de tareas."""
        interval = .3

        while True:
            ok_task = []
            failed_task = []
            res_monitor = self.POSTMAN.MonitorSpecificService(auth['user'], self.TOKEN_SOLUTION, list_of_task, kind="subtask_list")
            
            if res_monitor['status'] == "OK":
                for tsk in list_of_task:
                    if tsk in res_monitor["list_task"]:
                        task_info = res_monitor["list_task"][tsk]
                        if task_info['status'] in ["OK", "FINISHED"]:
                            ok_task.append(tsk)
                        if task_info['status'] in ["ERROR", "FAILED"]:
                            failed_task.append(tsk)
                    else:
                        self.LOGER.error("Monitoreando tarea inexistente: %s" % tsk)
            else:
                self.LOGER.error("El monitor no devolvio nada")

            if len(list_of_task) == (len(ok_task) + len(failed_task)):
                break
            time.sleep(interval)
            
        return ok_task

    def run_pattern(self, pattern_info, data_path, auth, dag):
        """
        Ejecuta la lógica core del patrón distribuido. Fragmenta los datos, 
        despacha los workers, monitorea y consolida los resultados.
        """
        def SendData(listOfTask, listDataMap):
            i = 0
            for id_task in listOfTask:
                data_map = listDataMap[i]
                ToSend = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION, "Data preparation", "INIT", id_service=id_task, label=id_task, type_data="csv", index_opt=True)
                self.POSTMAN.WarnGateway(ToSend)

                self.POSTMAN.ArchiveData(data_map['data'], "subset.csv", id_service=id_task, mining_statistics=True)
                
                ToSend = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION, "Data indexed", "FINISHED", id_service=id_task, label=id_task, type_data="csv", index_opt=True, include_hash=True)
                self.POSTMAN.WarnGateway(ToSend)

                i += 1
                os.remove(data_map['data'])
            self.LOGER.info(f"Datos despachados: {i}")
            return True

        kind_pattern = pattern_info['kind']
        workers = int(pattern_info['workers'])
        levels = pattern_info['spec']['variables']

        reduce_mode = pattern_info['spec'].get('reduce_mode', 'dummy')
        if_limit = pattern_info.get('limit_threads', True)
        level_to_process = pattern_info['spec'].get('level_to_process', [str(i) for i in range(1, len(levels) + 1)])

        output_name = "reduce.csv"
        output_datatype = "csv"

        sub_child = dag.copy()
        substack_id = "%s-subgraph-%s" % (self.SERVICE_ID, self.TOKEN_SOLUTION) 

        if 'pattern' in sub_child:
            del sub_child['pattern']
        sub_child['children'] = []
        endpoints = [sub_child]

        self.LOGER.info("---------------------------- DEPLOYING SUBGRAPH...")
        GC.start_services({
                "DAG": endpoints,
                "id_stack": substack_id,
                "mode": "compose",
                "engine": "nez",
                "replicas": workers})
        self.LOGER.info("---------------------------- DEPLOYED...")

        dispatcher_client = BB_dispatcher.bb_dispatcher(self.TOKEN_SOLUTION, self.SERVICE_ID, substack_id, LOGER=self.LOGER, POSTMAN=self.POSTMAN)

        # ============================ FASE MAP ===============================
        self.LOGER.info("---------------------------- MAP PROCESS ---------------------------- ")
        original_dataset = pd.read_csv(data_path['data'])
        list_of_task = []
        list_of_datamap = []
        n_levels = len(levels)
        
        for col in levels:
            original_dataset[col] = original_dataset[col].astype(str)
            
        list_porducts = self.list_tasks_by_pattern(sub_child, level_to_process) 
        xelhua = {"path": "L1=val1", "levels": {}, "products": list_porducts}
        
        for lvl_idx in range(n_levels): 
            selected_levels = levels[0:lvl_idx+1]
            dataset = original_dataset.groupby(selected_levels)
            self.LOGER.info("Creando particiones para: %s" % selected_levels)

            id_values = 0
            for name, group in dataset:
                name = [name] if not isinstance(name, tuple) else name 
                lvl = len(name) 

                if str(lvl) not in xelhua['levels']:
                    xelhua["levels"][str(lvl)] = {"id": str(lvl), "name": levels[lvl_idx], "values": {}}

                formated_names = []
                form_name = name[-1].split(".")[0] 
                
                if form_name not in xelhua["levels"][str(lvl)]["values"]:
                    xelhua["levels"][str(lvl)]["values"][form_name] = {"id": id_values, "name": form_name, "children": {}}
                    id_for_parents = id_values
                    id_values += 1
                else:
                    id_for_parents = xelhua["levels"][str(lvl)]["values"][form_name]['id']

                for i in range(len(name)): 
                    form_name = name[i].split(".")[0]
                    if i != lvl_idx:
                        if str(lvl) not in xelhua["levels"][str(i+1)]["values"][form_name]['children']:
                            xelhua["levels"][str(i+1)]["values"][form_name]['children'][str(lvl)] = []
                        if id_for_parents not in xelhua["levels"][str(i+1)]["values"][form_name]['children'][str(lvl)]:
                            xelhua["levels"][str(i+1)]["values"][form_name]['children'][str(lvl)].append(id_for_parents)
                    
                    group.loc[:, selected_levels[i]] = name[i]
                    formated_names.append("%s=%s" % (selected_levels[i], form_name))

                id_group = "-VAL-".join(formated_names).replace("/", "") 
            
                data_map = self.CreateDataMap(group, id_group)
                list_of_task.append("%s-LVL-%s-MAP-%s" % (lvl, id_group, self.SERVICE_ID)) 
                list_of_datamap.append(data_map)
                del group

        del dataset, original_dataset 
        
        self.POSTMAN.VisualProducts_Map_Manager("create", self.TOKEN_SOLUTION, token_dispatcher=self.SERVICE_ID, data_obj=xelhua)
        self.LOGER.info("-------------- data partitions created: %s " % len(list_of_task))

        thread1 = mp.Process(target=SendData, args=(list_of_task, list_of_datamap))
        thread1.start()
        self.TH_MONITOR.AppendThread(thread1)

        # =========================== DISPATCH & SHUFFLE =============================
        metadata = {"list_task": list_of_task, "context": substack_id, "levels": levels, "dispatcher": self.SERVICE_ID} 

        list_of_task = []
        for task in metadata['list_task']:
            lvl = task.split("-LVL-")[0]
            if lvl in level_to_process or "all" in level_to_process: 
                id_father_task = sub_child['id']
                id_group = task.split("-MAP-")[0] 
                list_of_task.append("%s-subtask-%s" % (id_group, id_father_task)) 

        self.LOGER.info("Subtareas detectadas: %s" % len(list_of_task))
        res_monitor = self.POSTMAN.ValidateSubtask(self.TOKEN_SOLUTION, list_of_task)['value'].get("task_list", {})  
        self.LOGER.info("Subtareas previamente ejecutadas: %s" % len(res_monitor))

        treshold = 0
        cummulative_treshold = 0
        list_dags = []
        n_task = len(list_of_task)

        with tempfile.NamedTemporaryFile(delete=False, mode='w+', encoding='utf-8') as temp_file:
            temp_file.write("Este es un archivo temporal con contenido")
            temp_file_path = temp_file.name  

        for task in metadata['list_task']: 
            lvl = task.split("-LVL-")[0]
            if lvl in level_to_process or "all" in level_to_process: 
                temp = sub_child.copy()
                data_map = {"data": {"token": self.TOKEN_SOLUTION, "task": task}, "type": "SOLUTION"}
                data_pointer = open(temp_file_path, "rb")
                dag_to_send = self.CloneDict(self.Prepare_subdag_instance_v2(temp, task))
                ENV_VARS = self.GetSubtaskContextVariables(task)
                
                if dag_to_send['id'] not in res_monitor: 
                    self.LOGER.info("Enviando a sub-hijo: %s" % dag_to_send['id'])
                    dispatcher_client.Send_to_BB(data_map, data_pointer, auth, dag_to_send, parent=task, ENV=ENV_VARS)
                    treshold += 1
                    cummulative_treshold += 1
                    list_dags.append(dag_to_send)
                
                    if treshold == workers:
                        self.LOGER.info("================ %s pipes enviados... esperando (total: %s) ===============" % (cummulative_treshold, n_task))
                        list_dags = self.MonitoringByDAG(list_dags, auth)
                        treshold = len(list_dags)
                        
        self.LOGER.info("---------------------------- MAP DISPATCH FINISHED...")

        # ============================ FASE REDUCE ===============================
        self.Monitoring(list_of_task, auth)
        self.LOGER.info("---------------------------- Join process: %s" % reduce_mode)

        if reduce_mode == "concat":
            df_list = []
            for tsk in list_of_task:
                try:
                    restuls_map = self.POSTMAN.GetResults(self.TOKEN_SOLUTION, tsk, auth)
                    df_list.append(pd.read_csv(restuls_map['data']))
                except Exception as e:
                    self.LOGER.error("No data from %s" % tsk)

            concat_DF = pd.concat(df_list, ignore_index=True)
            concat_DF.to_csv(self.BBOX_OUTPUT_PATH + output_name, index=False)
            del concat_DF
            return {"data": self.BBOX_OUTPUT_PATH + output_name, "type": output_datatype, "status": "OK", "message": "Pattern complete"}
    
        else: # Dummy mode
            f = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
            f.write(b"dummy,dummy,dummy\n0,0,0")
            fname = f.name
            f.close()
            return {"data": fname, "type": "csv", "status": "OK", "message": "Pattern complete (Dummy)"}