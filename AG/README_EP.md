## 1) Estado y sesion

### GET /

- Descripcion: valida que el gateway este disponible.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:180`
- Parametros:
  - Header: `x-access-token`.
- Resultado:
  - `200 OK` con `{"status":"OK","message":"xel is online."}`.

### GET /health

- Descripcion: health check simple del proceso.
- Autenticacion: no requerida.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:185`
- Parametros: sin parametros.
- Resultado:
  - `200 OK` con `{"status":"OK"}`.

### POST /signup

- Descripcion: registra un usuario nuevo; puede inicializar ejemplos si la configuracion lo permite.
- Autenticacion: no requerida.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:189`
- Parametros:
  - Body JSON:
    - `username` (string)
    - `email` (string)
    - `password` (string)
- Resultado:
  - `200 OK` en registro exitoso.
  - `4xx/5xx` segun validacion o error interno.

### POST /login

- Descripcion: inicia sesion con auth y crea sesion distribuida.
- Autenticacion: no requerida.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:201`
- Parametros:
  - Body JSON:
    - `user` (string)
    - `password` (string)
- Resultado:
  - `200 OK` con `access_token` y `tokenuser` (habitualmente).
  - `401` si credenciales invalidas.

### POST /logout

- Descripcion: invalida la sesion actual.
- Autenticacion: no requerida por decorador, pero requiere datos de sesion validos.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:206`
- Parametros:
  - Body JSON:
    - `tokenuser` (string)
    - `access_token` (string)
- Resultado:
  - `200 OK` cuando cierra sesion correctamente.

## 2) Gestion de servicios y publicacion

### POST /ADD

- Descripcion: registra recurso o instancia de servicio en memoria distribuida.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:211`
- Parametros:
  - Body JSON:
    - `SERVICE` (string)
    - `ID` (string)
    - `IP` (string)
    - `PORT` (number)
    - `CONTEXT` (string)
- Resultado:
  - `200 OK` si se registra correctamente.
  - `503` si memoria distribuida rechaza la operacion.

### POST /publish

- Descripcion: publica una solucion para compartirla.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:226`
- Parametros:
  - Body JSON:
    - `token_solution` (string)
    - `token_user` (string)
- Resultado:
  - `200 OK` con token publico o confirmacion de publicacion.

### POST /unpublish

- Descripcion: elimina la publicacion de una solucion.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:237`
- Parametros:
  - Body JSON:
    - `token_solution` (string)
- Resultado:
  - `200 OK` si se retira la publicacion.

### POST /get_published

- Descripcion: recupera una solucion publicada por token publico.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:248`
- Parametros:
  - Body JSON:
    - `public_token` (string)
- Resultado:
  - `200 OK` con informacion de la solucion publicada.
  - `404` si no existe.

### POST /ASK

- Descripcion: reenvia consulta al gateway/postman para interaccion con servicios.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:260`
- Parametros:
  - Body JSON variable segun `postman.AskGateway`.
- Resultado:
  - `200 OK` con respuesta del servicio objetivo.

### GET /STATUS

- Descripcion: devuelve estado de servicios registrados en la malla.
- Autenticacion: no requerida actualmente.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:267`
- Parametros: sin parametros.
- Resultado:
  - `200 OK` con estado global de servicios.

### POST /WARN

- Descripcion: registra y propaga advertencia al gateway.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:284`
- Parametros:
  - Body JSON libre con mensaje de advertencia.
- Resultado:
  - `200 OK` con confirmacion de registro.

## 3) Orquestacion de DAGs

### POST /deploy

- Descripcion: registra y despliega nodos para una solucion, sin ejecutar.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:300`
- Parametros:
  - Body JSON:
    - `DAG` (string JSON)
    - `auth` (objeto)
    - `alias` (string, opcional)
    - `metadata` (objeto, opcional)
    - `dataobject` (objeto, opcional)
    - `options.force` (bool, opcional)
- Resultado:
  - `200 OK` con `token_solution` y DAG a desplegar.

### POST /removestack

- Descripcion: detiene y elimina stack asociado a una solucion desplegada.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:354`
- Parametros:
  - Body JSON:
    - `token_solution` (string)
    - `auth` (objeto)
- Resultado:
  - `200 OK` si elimina correctamente.
  - `404` si no existe la solucion.

### POST /executeDAG

- Descripcion: ejecuta DAG sobre una fuente de datos.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:392`
- Parametros:
  - Body JSON:
    - `DAG` (string JSON)
    - `data_map` (objeto con `type` y `data`)
    - `auth` (objeto)
    - `metadata` (objeto, opcional)
    - `dataobject` (objeto, opcional)
    - `options.force` (bool, opcional)
- Resultado:
  - `202 Accepted` con `token_solution`, `DAG`, `is_already_running`.

### GET|POST /monitor/v2/<token_project>/<token_solution>

- Descripcion: consulta estado de una solucion y puede recuperar subtareas fallidas.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:484`
- Parametros:
  - Path:
    - `token_project` (string)
    - `token_solution` (string)
  - Body opcional para POST:
    - `tasks` (array de strings)
    - `kind_task` (string)
    - `show_history` (bool)
- Resultado:
  - `200 OK` con estado de tareas/solucion.

### GET /stopDAG/<token_project>/<token_solution>

- Descripcion: fuerza paro de servicios de una solucion.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:292`
- Parametros:
  - Path:
    - `token_project` (string)
    - `token_solution` (string)
- Resultado:
  - Operacion administrativa. La implementacion actual puede no retornar respuesta HTTP consistente.

### POST /report_time

- Descripcion: almacena metricas de tiempo de una solucion.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:273`
- Parametros:
  - Body JSON:
    - `token_solution` (string)
    - `times` (objeto con campos como `id`, `acq`, `serv`, `trans`, `exec`, `idx`, `comm`)
- Resultado:
  - `200 OK` con confirmacion de registro.

### POST /exec

- Descripcion: endpoint reservado para ejecucion directa de recurso con archivo adjunto.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:373`
- Parametros:
  - Entrada multipart/form-data + campos internos.
- Resultado:
  - Implementacion incompleta; contrato de respuesta no estable.

## 4) Metadatos de ejecucion y productos

### POST /ProductsObjectMap

- Descripcion: opera sobre mapa de objetos de producto en memoria distribuida.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:550`
- Parametros:
  - Body segun contrato interno `PRODUCTS_MAP`.
- Resultado:
  - `200 OK` si la operacion es valida.

### POST /Validate_subtask_executions

- Descripcion: valida si una subtask ya fue ejecutada.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:561`
- Parametros:
  - Body segun contrato interno `VALIDATE_SUBTASK_EXE`.
- Resultado:
  - `200 OK` con resultado de validacion.

### POST /ArchiveData/<token_solution>/`<task>`

- Descripcion: endpoint interno para almacenar resultado de tarea y metadata.
- Autenticacion: API_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:800`
- Parametros:
  - Path:
    - `token_solution` (string)
    - `task` (string)
  - Request multipart o payload binario.
  - Cookie opcional `metadata` con `product_name`.
- Resultado:
  - `200 OK` con confirmacion de archivado.

### POST /metadata/insert/<token_solution>/`<task>`

- Descripcion: inserta metadata de producto sin subir archivo.
- Autenticacion: API_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:818`
- Parametros:
  - Path:
    - `token_solution` (string)
    - `task` (string)
  - Cookie opcional `metadata` con `product_name`.
- Resultado:
  - `200 OK` con confirmacion.

### GET /metadata/get/<token_solution>

- Descripcion: recupera metadatos de productos de una solucion.
- Autenticacion: no requerida actualmente.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:833`
- Parametros:
  - Path:
    - `token_solution` (string)
- Resultado:
  - `200 OK` con metadatos y generacion de `list_products.csv`.

### GET /locate/`<RN>`/`<task>`

- Descripcion: endpoint marcado como deprecated; localiza recurso de una tarea.
- Autenticacion: no requerida.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:847`
- Parametros:
  - Path:
    - `RN` (string)
    - `task` (string)
- Resultado:
  - `200 OK` con ubicacion cuando aplica.

## 5) Recuperacion y administracion de soluciones

### POST /solution/store

- Descripcion: guarda una solucion para reutilizacion y listado posterior.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:649`
- Parametros:
  - Body JSON:
    - `auth` (objeto)
    - `metadata` (objeto con `name`, `desc`, `frontend`, etc.)
    - `DAG` (string JSON)
- Resultado:
  - `200 OK` con `info.token_solution`.

### POST /solution/retrieve

- Descripcion: recupera una solucion almacenada.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:611`
- Parametros:
  - Body JSON:
    - `auth` (objeto)
    - `token_solution` (string)
- Resultado:
  - `200 OK` con detalle de la solucion.
  - `404` si no existe.

### POST /solution/delete

- Descripcion: elimina una solucion de memoria distribuida y carpeta local asociada.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:626`
- Parametros:
  - Body JSON:
    - `auth` (objeto)
    - `token_solution` (string)
- Resultado:
  - `200 OK` si elimina correctamente.

### POST /solution/list

- Descripcion: lista soluciones de un usuario.
- Autenticacion: token_required + resource_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:670`
- Parametros:
  - Body JSON:
    - `auth` (objeto)
    - `params` (objeto opcional para filtros)
- Resultado:
  - `200 OK` con arreglo/listado de soluciones.

## 6) Workspaces y datasets

### GET /workspace/create/`<tokenuser>`/`<workspace>`

- Descripcion: crea workspace del usuario si no existe.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:692`
- Parametros:
  - Path:
    - `tokenuser` (string)
    - `workspace` (string)
- Resultado:
  - `200 OK` con confirmacion.

### GET /workspace/delete/`<tokenuser>`/`<workspace>`

- Descripcion: elimina workspace completo.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:698`
- Parametros:
  - Path:
    - `tokenuser` (string)
    - `workspace` (string)
- Resultado:
  - `200 OK` con confirmacion.

### GET /workspace/list/`<tokenuser>`

- Descripcion: lista workspaces del usuario.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:704`
- Parametros:
  - Path:
    - `tokenuser` (string)
- Resultado:
  - `200 OK` con listado.

### GET /workspace/list/`<tokenuser>`/`<workspace>`

- Descripcion: lista contenido detallado de un workspace.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:710`
- Parametros:
  - Path:
    - `tokenuser` (string)
    - `workspace` (string)
- Resultado:
  - `200 OK` con archivos y/o carpetas.

### GET /workspace/getfile/`<tokenuser>`/`<workspace>`/`<filename>`

- Descripcion: descarga un archivo del workspace.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:717`
- Parametros:
  - Path:
    - `tokenuser` (string)
    - `workspace` (string)
    - `filename` (string)
- Resultado:
  - `200 OK` con archivo adjunto.
  - `404` si no existe.

### GET /workspace/delete/`<tokenuser>`/`<workspace>`/`<filename>`

- Descripcion: elimina un archivo y su descriptor `.json` asociado si existe.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:779`
- Parametros:
  - Path:
    - `tokenuser` (string)
    - `workspace` (string)
    - `filename` (string)
- Resultado:
  - `200 OK` con confirmacion de borrado.

### POST /UploadDataset

- Descripcion: sube un dataset al workspace.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:728`
- Parametros:
  - Form-data:
    - `file` (archivo)
    - `workspace` (string)
    - `user` (token_user)
- Resultado:
  - `200 OK` con confirmacion y metadata de carga.

### POST /CreatePackage

- Descripcion: empaqueta archivos en zip dentro de workspace destino.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:745`
- Parametros:
  - Body JSON:
    - `tokenuser` (string)
    - `name_package` (string)
    - `list_files` (array de strings)
    - `destination` (string)
    - `force_cration` (bool)
- Resultado:
  - `200 OK` con ruta o nombre del paquete generado.

## 7) Acceso a archivos y consulta de datos

### POST /getfile

- Descripcion: descarga archivo de entrada o producto usando referencia abstracta.
- Autenticacion: token_required + data_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:574`
- Parametros:
  - Body JSON:
    - `type` (ej. `LAKE`, `SOLUTION`)
    - `data` (objeto con `token_user`, `catalog`, `filename`, etc.)
- Resultado:
  - `200 OK` con archivo.
  - `406` si dataset no esta disponible.

### POST /DatasetQuery

- Descripcion: ejecuta consultas simples sobre datasets (ej. unique, query, inside).
- Autenticacion: token_required + data_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:859`
- Parametros:
  - Body JSON:
    - `type` (string)
    - `data` (objeto de dataset)
    - `ask` (array de objetos de consulta)
- Resultado:
  - `200 OK` con resultado de la consulta.

### POST /DescribeDataset/v2

- Descripcion: genera descripcion estructurada de dataset o zip; reutiliza cache cuando aplica.
- Autenticacion: token_required + data_autorization_requiered.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:895`
- Parametros:
  - Body JSON:
    - `type` (string)
    - `data` (objeto de dataset)
    - `delimiter` (string, opcional)
    - `force` (bool, opcional)
- Resultado:
  - `200 OK` con descriptor del dataset.
  - `406` si no se puede acceder al archivo.

## 8) Referencias y logs

### POST /reference/get

- Descripcion: resuelve valor de referencia desde tablas configuradas y variables de entorno.
- Autenticacion: no requerida.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:951`
- Parametros:
  - Body JSON:
    - `query` (string)
    - `ENV` (objeto clave-valor)
- Resultado:
  - `200 OK` con valor de referencia resuelto.

### GET /getlog/`<RN>`

- Descripcion: descarga log asociado a una solucion.
- Autenticacion: token_required.
- Ubicacion en codigo: `AG/app/coordinator_middleware.py:1001`
- Parametros:
  - Path:
    - `RN` (string)
- Resultado:
  - `200 OK` con archivo de log.

puedeshacerme una tabla con esta informacion para cada uno de los apartados, seria una tabla por apartado
