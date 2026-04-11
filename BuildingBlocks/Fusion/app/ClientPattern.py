import time
import logging
import json
import pandas as pd
from shared_components import genesis_client as GC
from shared_components import BB_dispatcher 
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from threading import Thread
from shared_components.ThreadCreator import threadMonitor
import multiprocessing as mp

import os
#from TPS.Builder import Builder #TPS API BUILDER

class client_pattern():

    def __init__(self,TOKEN_SOLUTION,SERVICE_ID,LOGER=None,POSTMAN=None,Monitor_Threads=None):
        
        if LOGER is None:
            self.LOGER = logging.getLogger()
        else:
            self.LOGER=LOGER

        if LOGER is None:
            self.TH_MONITOR = threadMonitor()
        else:
            self.TH_MONITOR=Monitor_Threads

        ####
        self.TOKEN_SOLUTION=TOKEN_SOLUTION
        self.SERVICE_ID=SERVICE_ID
        self.POSTMAN=POSTMAN
        # output path
        self.BBOX_OUTPUT_PATH=tempfile.mkdtemp() +"/"

    def CreateDataMap(self,data,id):
        file_group = tempfile.NamedTemporaryFile(delete=False,suffix=".csv",prefix=id+"-GROUP-") # TEMPORARY FILE TO SAVE DATA
        data.to_csv(file_group,index=False)
        fname = file_group.name
        data_map = {"data":fname,"type":"csv"}
        file_group.close()
        return data_map

    def CloneDict(self,dict_obj):
        return json.loads(json.dumps(dict_obj))


    def GetSubtaskContextVariables(self, id_str):
        dict_var_context = {}
        string_context = id_str.replace("-VAL-","/")
        string_context = string_context.replace("-LVL-","/")
        string_context = string_context.replace("-MAP-","/")
        string_context = string_context.replace("-subtask-","/")
        string_arr = string_context.split("/")
        for var in string_arr:
            key_val = var.split("=")
            if len(key_val)==2:
                dict_var_context[key_val[0]] =key_val[1]
        return dict_var_context
            

    def Prepare_subdag_instance_v2(self,dag,task,as_original = False):
        if not as_original: #keep the original ID
            id_group = task.split("-MAP-")[0] #se obtiene el id_group
            dag['id'] = "%s-subtask-%s" % (id_group,dag['id']) #c-subtask-a-subtask-imputation
        return dag

    def Corroborate_pipe_finished(self,dag,list_task):
        if dag['id'] in list_task: #verify childs
            task_info = list_task[dag['id']]
            if task_info['status']=="OK" or task_info['status']=="FINISHED" or task_info['status']=="ERROR" or task_info['status']=="FAILED":
                for ch in dag['children']:
                    if not self.Corroborate_pipe_finished(ch,list_task):
                        return False
            else:
                return False
        else:
            return False
        return True

    def list_tasks_in_DAGs(self,list_dags,list_tasks=[]):
        for dag in list_dags:
            list_tasks.append(dag['id'])
            list_tasks = self.list_tasks_in_DAGs(dag['children'],list_tasks)
        return list_tasks

    def list_tasks_in_DAGs_by_pattern(self,list_dags,task_obj={}):
        for dag in list_dags:
            if 'pattern' in dag:
                if (dag['pattern']['kind']=="Chain" or dag['pattern']['kind']=="Reduce") and dag['pattern']['active']:
                    levels_to_process = dag['pattern']['spec']['level_to_process'] # 1,2,3,n ... all:::str()
                    for l in levels_to_process:
                        if not l in task_obj:
                            task_obj[l]={} 
                        task_obj[l][dag['id']] ={"id":dag["id"],"alias":dag["alias"],"service":dag["service"],"params":dag["params"]}
            
            task_obj = self.list_tasks_in_DAGs_by_pattern(dag['children'],task_obj)
        return task_obj

    def list_tasks_by_pattern(self,dag,levels_to_process):
        task_obj={}
        for l in levels_to_process:
            if not l in task_obj:
                task_obj[l]={} 
            task_obj[l][dag['id']] ={"id":dag["id"],"alias":dag["alias"],"service":dag["service"],"params":dag["params"]}
        return task_obj

    def MonitoringByDAG(self,list_of_dags,auth):
        interval = .3
        max_attempts=150
        att=0
        list_task =self.list_tasks_in_DAGs(list_of_dags,list_tasks=[])
        #self.LOGER.error(len(list_of_dags))
        #self.LOGER.error(len(list_task))

        while(True):

            on_waiting = []
            res_monitor = self.POSTMAN.MonitorSpecificService(auth['user'],self.TOKEN_SOLUTION,list_task,kind="subtask_list")
            att+=1
            if res_monitor is not None:
            
                if res_monitor['status']=="OK":
                    for dag in list_of_dags:
                        if_finished = self.Corroborate_pipe_finished(dag,res_monitor["list_task"])
                        if not if_finished:
                            on_waiting.append(dag)

                else:
                    self.LOGER.error("El monitor no devolvio nada")

                #todas terminaron
                if len(on_waiting) < len(list_of_dags):
                    break
                if att>max_attempts:
                    self.LOGER.error("aun estamos esperando las siguientes tareas")
                    self.LOGER.error(on_waiting)
                    att=0

                time.sleep(interval)

        return on_waiting

    def Monitoring(self,list_of_task,auth):
        interval = .3

        while(True):
            ok_task = []
            failed_task =[]
            res_monitor = self.POSTMAN.MonitorSpecificService(auth['user'],self.TOKEN_SOLUTION,list_of_task,kind="subtask_list")
            #res_monitor = self.POSTMAN.MonitorService(auth['user'],self.TOKEN_SOLUTION)
            if res_monitor['status']=="OK":
                for tsk in list_of_task:
                    if tsk in res_monitor["list_task"]:
                        task_info = res_monitor["list_task"][tsk]
                        if task_info['status']=="OK" or task_info['status']=="FINISHED":
                            ok_task.append(tsk)
                            pass
                        if task_info['status']=="ERROR" or task_info['status']=="FAILED":
                            failed_task.append(tsk)
                        if task_info['status']=="WAITING" or task_info['status']=="RUNNING":
                            pass
                    else:
                        self.LOGER.error("estoy monitoreando una tarea queno existe %s" % tsk)
            else:
                self.LOGER.error("El monitor no devolvio nada")

            #todas terminaron
            if len(list_of_task) == (len(ok_task)+len(failed_task)):
                break
            time.sleep(interval)
        return ok_task

    def run_pattern(self, pattern_info,data_path,auth,dag):
        """
        {
            kind: MR;MW;DQ ::str()
            workers: ::int()
            spec:{
                // for map reduce (MR)
                variables::list[]
                on_cascade::boolean
                reduce::chunk;fusion::str() //always
            }
        }

        """
        def SendData(listOfTask,listDataMap):
            # NOTA PARA ARMANDO DEL FUTURO: esta funcion se puede paralelizar, porque el hash se crea en ArchiveData, es decir que se sobreescribirian los hash al hacerlos en paralelo
            # la solucion es instancias nuevos POSTMAN para cada lista de tareas en paralelo
            i=0
            for id_task in listOfTask:
                data_map=listDataMap[i]

                ToSend = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION,"Data preparation","INIT",id_service=id_task,label=id_task,type_data="csv",index_opt=True)
                self.POSTMAN.WarnGateway(ToSend)

                self.POSTMAN.ArchiveData(data_map['data'],"subset.csv",id_service=id_task,mining_statistics=True)
                
                ToSend = self.POSTMAN.CreateMessage(self.TOKEN_SOLUTION,"Data indexed","FINISHED",id_service=id_task,label=id_task,type_data="csv",index_opt=True,include_hash=True)
                self.POSTMAN.WarnGateway(ToSend)

                i+=1
                os.remove(data_map['data'])
            self.LOGER.info(i)
            return True

        kind_pattern = pattern_info['kind']
        workers = int(pattern_info['workers'])

        levels = pattern_info['spec']['variables']


        # parameters recived from frontend [patterns]
        reduce_mode = pattern_info['spec']['reduce_mode'] if 'reduce_mode' in pattern_info['spec'] else 'dummy'
        if_limit = pattern_info['limit_threads'] if 'limit_threads' in pattern_info else True
        level_to_process = pattern_info['spec']['level_to_process'] if 'level_to_process' in pattern_info['spec'] else [str(i) for i in range(1, len(levels) + 1)]


        #output name for reduce dataset
        output_name = "reduce.csv";output_datatype="csv"

        sub_child = dag.copy()
        substack_id = "%s-subgraph-%s" %(self.SERVICE_ID,self.TOKEN_SOLUTION) #new context

        #se hace una copia del dag original y se eliminan los child 
        # se eliminan los child para la copia del 
        
        del sub_child['pattern']
        sub_child['children']=[]
        endpoints = [sub_child]

        self.LOGER.error("---------------------------- DEPLOYING SUBGRAPH...")
        GC.start_services({
                "DAG":endpoints,
                "id_stack": substack_id,
                "mode":"compose",
                "engine":"nez",
                "replicas": workers})
        self.LOGER.error("----------------------------DEPLOYED...")

        #instance dispatcher 
        dispatcher_client = bb_dispatcher(self.TOKEN_SOLUTION,self.SERVICE_ID,substack_id,LOGER=self.LOGER,POSTMAN=self.POSTMAN)
        #create a output file in case of error

        self.LOGER.error("----------------------------sending instructions to subtask...")

        #================================================================#
        #============================ MAP ===============================#
        #================================================================#

        self.LOGER.info("----------------------------MAP PROCESS ---------------------------- ")
        
        original_dataset= pd.read_csv(data_path['data'])
        list_of_task = []; list_of_datamap = []
        n_levels = len(levels)
        original_dataset[levels] = original_dataset[levels].astype(str)
        list_porducts = self.list_tasks_by_pattern(sub_child,level_to_process) #obj
        xelhua ={"path":"L1=val1","levels":{},"products":list_porducts};
        
        #Create data partitions
        for lvl_idx in range(n_levels): 
            selected_levels=levels[0:lvl_idx+1]
            dataset = original_dataset.groupby(selected_levels)
            self.LOGER.info("----------------------------Se crean los grupos %s" % selected_levels)

            id_values =0
            for name, group in dataset:
            
                name = [name] if not isinstance(name, tuple) else name # e.g. City , (City,Gender)
                lvl = len(name) #nivel actual

                if str(lvl) not in xelhua['levels']:
                    xelhua["levels"][str(lvl)]={"id":str(lvl),"name":levels[lvl_idx],"values":{}}

                #se añaden los valores a la tabla y se eliminan valores decimales incecesarios
                formated_names = []
                form_name =name[-1].split(".")[0] #se toma el ultimo valor de la lista name
                if not form_name in xelhua["levels"][str(lvl)]["values"]:
                    xelhua["levels"][str(lvl)]["values"][form_name]={"id":id_values,"name":form_name,"children":{}}
                    id_for_parents = id_values
                    id_values+=1
                else:
                    id_for_parents= xelhua["levels"][str(lvl)]["values"][form_name]['id']

                for i in range(len(name)): #for each partition (e.g in a partition (City,Gender))
                    form_name =name[i].split(".")[0]
                    if i != lvl_idx:
                        if not str(lvl) in xelhua["levels"][str(i+1)]["values"][form_name]['children']:
                            xelhua["levels"][str(i+1)]["values"][form_name]['children'][str(lvl)]=[]
                        # se veirifica si ya existe el valor en la lista de children. si no existe se agrega
                        if not id_for_parents in xelhua["levels"][str(i+1)]["values"][form_name]['children'][str(lvl)]:
                            xelhua["levels"][str(i+1)]["values"][form_name]['children'][str(lvl)].append(id_for_parents)
                    group[selected_levels[i]]=name[i]
                    formated_names.append("%s=%s" %(selected_levels[i],form_name))

                id_group = "-VAL-".join(formated_names).replace("/", "") # 1-LVL-a=1-VAL-b=2-VAL-c=3-MAP-IdService
            
                # CREATE DATAFRAME OF PARTITION
                data_map = self.CreateDataMap(group,id_group)
                list_of_task.append("%s-LVL-%s-MAP-%s" % (lvl,id_group,self.SERVICE_ID)) #ID : c-subtask-a-subtask-imputation
                list_of_datamap.append(data_map)
                del group

        del dataset,original_dataset #delete original dataset
        
        #============================ verificacion ===============================#
        # si se ejecuta nuevamente es porque el dataset cambio, por tanto se verificara si el dataset crecio y, por tanto, si existe un json indexado
        self.POSTMAN.VisualProducts_Map_Manager("create",self.TOKEN_SOLUTION,token_dispatcher=self.SERVICE_ID,data_obj=xelhua)
        self.LOGER.info("-------------- data partitions created: %s " % len(list_of_task))

        #se suben todos lod atasets, pero se hace en segundo plano
        thread1 = mp.Process(target = SendData, args = (list_of_task,list_of_datamap)).start()
        self.TH_MONITOR.AppendThread(thread1)
        #============================ verificacion ===============================#

        #==========================================================================#
        #=========================== PARTITION SUFFLE =============================#
        #==========================================================================#

        metadata = {"list_task":list_of_task,"context":substack_id,"levels":levels,"dispatcher":self.SERVICE_ID} #just one dispatcher

        #============================ verificacion ===============================# clientpattern
        # aqui se verificara si el dataset crecio y, por tanto, si existe un json indexado
        # 1.- si este proceso se ejecuta entonces es porque el abox es nuevo o cambiaron los parametros. en cualquier caso se debe añadir al grafo de visualizacion (pasa cuando el abox es nuevo) 
        
        #temp = self.CloneDict(sub_child) #sub_child.copy()
        #temp = self.Prepare_subdag_instance_v2(temp,'',as_original=True)
        #task_map = {"id":self.SERVICE_ID,"alias":"","service":temp["service"],"params":temp["params"]}
        #self.POSTMAN.VisualProducts_Map_Manager("update",self.TOKEN_SOLUTION,token_dispatcher=dispatcher ,token_producer=self.SERVICE_ID,data_obj=task_map,levels=level_to_process)

        # 2.- hay una tercera opcion, es cuando cambia el dataset, en este caso se debe ejecutar la siguiente funcion
        
        #funcion verify_list_abox_process() en el acepter. returna true o false
        # la funcion recibe el token_solution, task_id, 
        # 3.- se verifica si previamente fueron ejecutados cada una de las actividades con el hash de metadata. si el hash cambio o no existe entonces es porque es nuevo o cambiaron los parametros
        #   esto primero se puede saber verificando el hash del json de metadata
        #   - si esto no es asi, entonces la ejecucion es debido a que el dataset cambió o creció
        #   
        # ahora los abox reportaran el hash del producto en BB_dispatcher a sus hijos. y tambien reportaran el hash del producto producido en ArchiveData (lo hara el coordinador)
        #  4.- se verificara, para cada proceso, que el hash output del padre coincida con el hash input del hijo que esta almacenado
        #       - si no existe el hash input, output, o no coincide, entonces se ejecutara el proceso (TRUE) , si no se omitira porque el proceso es el mismo y ya se ha realizado anteriormente (False)
        
        # task to dispatch
        list_of_task = []
        for task in metadata['list_task']:
            lvl = task.split("-LVL-")[0]
            if lvl in level_to_process or "all" in level_to_process: # procesar solo las tareas del nivel correspondiente
                id_father_task = sub_child['id']
                id_group = task.split("-MAP-")[0] #se obtiene el id_group
                list_of_task.append("%s-subtask-%s" % (id_group,id_father_task)) #c-subtask-a-subtask-imputation

        #detect task that changed (e.g. dataset increased):
        self.LOGER.error("Subtareas detectadas: %s" % len(list_of_task))
        res_monitor = self.POSTMAN.ValidateSubtask(self.TOKEN_SOLUTION,list_of_task)['value']["task_list"]  
        self.LOGER.error("Subtareas previamente ejecutadas: %s" % len(res_monitor))


        treshold=0; cummulative_treshold = 0; list_dags = []
        n_task =len(list_of_task)

        #create temporal dataset to send to ABOXes (this is bc if we send nothing, sockets will join into a infinit bucle)
        with tempfile.NamedTemporaryFile(delete=False, mode='w+', encoding='utf-8') as temp_file:
            temp_file.write("Este es un archivo temporal con contenido")
            temp_file_path = temp_file.name  # Guardar la ruta del archivo temporal

        for task in metadata['list_task']: #esta lista representan las ramas del reduce, pero no el total de tareas a monitorear
            lvl = task.split("-LVL-")[0]
            if lvl in level_to_process or "all" in level_to_process: # procesar solo las tareas del nivel correspondiente
                temp = sub_child.copy()
                data_map = {"data":{"token":self.TOKEN_SOLUTION,"task":task},"type":"SOLUTION"}
                data_pointer = open(temp_file_path,"rb")
                dag_to_send =  self.CloneDict(self.Prepare_subdag_instance_v2(temp,task))
                ENV_VARS= self.GetSubtaskContextVariables(task)
                self.LOGER.error("----------------------------sending to subchild: %s"%dag_to_send['id'])
                if dag_to_send['id'] not in res_monitor: #si aun no se dispacha entones se a enviar
                    self.LOGER.error("----------------------------sending to subchild: %s"%dag_to_send['id'])
                    dispatcher_client.Send_to_BB(data_map,data_pointer,auth,dag_to_send,parent = task,ENV=ENV_VARS)
                    self.LOGER.error("----------------------------sent to subchild: %s"%dag_to_send['id'])
                    treshold+=1
                    cummulative_treshold +=1
                    list_dags.append(dag_to_send)
                
                    if treshold==workers:
                        self.LOGER.error("================ %s pipes sent... waiting %s (total task: %s) ===============" % (cummulative_treshold,len(list_dags),n_task))
                        list_dags = self.MonitoringByDAG(list_dags,auth)
                        treshold = len(list_dags)
        self.LOGER.error("----------------------------PATTERN FINISHED...")

        ##########################################
        #ahora hay que monitorear
        self.Monitoring(list_of_task,auth)
        self.LOGER.error("---------------------------- Join process: %s" %reduce_mode)
        ##########################################

        if reduce_mode=="concat":
            df_list = []
            for tsk in list_of_task:
                try:
                    restuls_map= self.POSTMAN.GetResults(self.TOKEN_SOLUTION,tsk,auth)
                    self.LOGER.info("se guardó el resultado de %s"%tsk)
                    df_list.append(pd.read_csv(restuls_map['data']))
                except Exception as e:
                    self.LOGER.error("no data from %s"%tsk)

            
            concat_DF = pd.concat(df_list)
            concat_DF.to_csv(self.BBOX_OUTPUT_PATH+output_name,index=False)
            del concat_DF
            return {"data":self.BBOX_OUTPUT_PATH+output_name,"type":output_datatype,"status":"OK","message":"Pattern complete"}
    
        else: #dummy
            f = tempfile.NamedTemporaryFile(suffix=".csv",delete=False)
            f.write("dummy,dummy,dummy\n0,0,0".encode())
            fname = f.name
            f.close()
            return {"data":fname,"type":"csv","status":"OK","message":"Pattern complete"}
        