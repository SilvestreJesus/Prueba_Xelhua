# API Gateway de Xelhua

Este documento describe la API expuesta por el coordinador de Xelhua, implementada en `AG/app/coordinator_middleware.py`.

## Resumen

- Framework: Flask + Waitress
- Puerto interno: `5555`
- Puerto publicado por defecto: `25000`
- URL base local habitual: `http://localhost:25000`
- Archivo principal de rutas: `AG/app/coordinator_middleware.py`

## Autenticacion

La mayor parte de la API espera el header:

```http
x-access-token: <access_token>
```

Hay tres niveles de validacion en el servicio:

- `@token_required`: valida que el token de sesion exista y no haya expirado.
- `@resource_autorization_requiered`: ademas valida que `auth.user` en el body pertenezca al token enviado.
- `@data_autorization_requiered`: ademas valida que `data.token_user` en el body pertenezca al token enviado.
- `@API_required`: restringe el acceso a llamadas internas entre servicios usando API key.

Cuando la variable de entorno `TOKEN_REQUIERD` esta desactivada, las rutas pueden funcionar sin autenticacion estricta.

## Convenciones de payload

Patrones comunes usados por varias rutas:

- `auth`: contexto del usuario que ejecuta una accion.

```json
{
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  }
}
```

- `data_map`: origen de datos a procesar.

```json
{
  "data_map": {
    "type": "LAKE",
    "data": {
      "token_user": "<token_user>",
      "catalog": "Examples",
      "filename": "archivo.csv"
    }
  }
}
```

Tipos admitidos en `data_map.type`:

- `LAKE`: archivo en el workspace del usuario.
- `SOLUTION`: producto generado por una solucion previa.
- `RECORDS`: registros crudos enviados inline.
- `SHARED`: producto compartido por otro usuario.
- `DUMMY`: marcador interno.

- `DAG`: grafo serializado como string JSON.

## Endpoints

### Estado y sesion

#### `GET /`

- Autenticacion: `token_required`
- Descripcion: valida que el gateway este disponible.
- Respuesta exitosa:

```json
{
  "status": "OK",
  "message": "xel is online."
}
```

#### `GET /health`

- Autenticacion: no requerida
- Descripcion: health check simple del proceso.
- Respuesta: `{"status":"OK"}`

#### `POST /signup`

- Autenticacion: no requerida
- Descripcion: registra un usuario nuevo. Si `ALLOW_REGISTER_NEW_USERS` esta activo, tambien inicializa ejemplos para ese usuario.
- Body esperado:

```json
{
  "username": "usuario",
  "email": "correo@dominio",
  "password": "secreto"
}
```

#### `POST /login`

- Autenticacion: no requerida
- Descripcion: inicia sesion contra el servicio de autenticacion y crea una sesion distribuida en Paxos.
- Body esperado:

```json
{
  "user": "usuario",
  "password": "secreto"
}
```

- Respuesta: normalmente incluye `access_token` y `tokenuser`.

#### `POST /logout`

- Autenticacion: no requerida a nivel decorador, pero requiere datos de sesion validos
- Descripcion: invalida la sesion actual.
- Body esperado:

```json
{
  "tokenuser": "<token_user>",
  "access_token": "<access_token>"
}
```

### Gestion de servicios y publicacion

#### `POST /ADD`

- Autenticacion: `token_required`
- Descripcion: registra un recurso o instancia de servicio en la memoria distribuida.
- Body esperado:

```json
{
  "SERVICE": "nombre_servicio",
  "ID": "id_instancia",
  "IP": "10.0.0.5",
  "PORT": 5000,
  "CONTEXT": "stack_o_contexto"
}
```

#### `POST /publish`

- Autenticacion: `token_required`
- Descripcion: publica una solucion para compartirla.
- Body minimo:

```json
{
  "token_solution": "<token_solution>",
  "token_user": "<token_user>"
}
```

#### `POST /unpublish`

- Autenticacion: `token_required`
- Descripcion: elimina la publicacion de una solucion.
- Body minimo:

```json
{
  "token_solution": "<token_solution>"
}
```

#### `POST /get_published`

- Autenticacion: `token_required`
- Descripcion: recupera una solucion publicada a partir de su token publico.
- Body minimo:

```json
{
  "public_token": "<public_token>"
}
```

#### `POST /ASK`

- Autenticacion: `token_required`
- Descripcion: reenvia una consulta al gateway/postman para interaccion con servicios.
- Body: depende del contrato esperado por `postman.AskGateway`.

#### `GET /STATUS`

- Autenticacion: no requerida actualmente
- Descripcion: devuelve el estado de los servicios registrados en la malla.

#### `POST /WARN`

- Autenticacion: `token_required`
- Descripcion: registra y propaga una advertencia al gateway.
- Body: objeto JSON libre con el mensaje de advertencia.

### Orquestacion de DAGs

#### `POST /deploy`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: registra y despliega los nodos necesarios para una solucion, sin ejecutarla.
- Body esperado:

```json
{
  "DAG": "<json_string>",
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  },
  "alias": "nombre opcional",
  "metadata": {},
  "dataobject": {},
  "options": {
    "force": true
  }
}
```

- Respuesta: `token_solution` y el DAG que necesita despliegue.

#### `POST /removestack`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: detiene y elimina el stack asociado a una solucion desplegada.
- Body esperado:

```json
{
  "token_solution": "<token_solution>",
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  }
}
```

#### `POST /executeDAG`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: ejecuta un DAG sobre una fuente de datos. Si la solucion no estaba corriendo, dispara los servicios raiz y continua la orquestacion.
- Body esperado:

```json
{
  "DAG": "<json_string>",
  "data_map": {
    "type": "LAKE",
    "data": {
      "token_user": "<token_user>",
      "catalog": "Examples",
      "filename": "dataset.csv"
    }
  },
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  },
  "metadata": {},
  "dataobject": {},
  "options": {
    "force": false
  }
}
```

- Respuesta: `202 Accepted` con `token_solution`, `DAG` e indicador `is_already_running`.

#### `GET|POST /monitor/v2/<token_project>/<token_solution>`

- Autenticacion: `token_required`
- Descripcion: consulta el estado de una solucion y, cuando aplica, intenta recuperar subtareas fallidas relanzando ejecuciones.
- Parametros de ruta:
  - `token_project`: token del usuario o proyecto.
  - `token_solution`: token de la solucion.
- Body opcional en `POST`:

```json
{
  "tasks": ["task1", "task2"],
  "kind_task": "task_list",
  "show_history": true
}
```

#### `GET /stopDAG/<token_project>/<token_solution>`

- Autenticacion: `token_required`
- Descripcion: fuerza el paro de los servicios asociados a una solucion y actualiza el monitoreo interno.
- Nota: la implementacion actual no devuelve explicitamente el `make_response`, por lo que conviene tratar esta ruta como operacion administrativa con comportamiento a revisar.

#### `POST /report_time`

- Autenticacion: `token_required`
- Descripcion: almacena metricas de tiempo de una solucion.
- Body esperado:

```json
{
  "token_solution": "<token_solution>",
  "times": {
    "id": "task_id",
    "acq": 0,
    "serv": 0,
    "trans": 0,
    "exec": 0,
    "idx": 0,
    "comm": 0
  }
}
```

#### `POST /exec`

- Autenticacion: `token_required`
- Descripcion: endpoint reservado para ejecucion directa de un recurso con archivo adjunto.
- Estado actual: la implementacion esta incompleta y no construye respuesta HTTP final.

### Metadatos de ejecucion y productos

#### `POST /ProductsObjectMap`

- Autenticacion: `token_required`
- Descripcion: opera sobre el mapa de objetos de producto en la memoria distribuida.
- Body: depende del contrato interno `PRODUCTS_MAP` de Paxos.

#### `POST /Validate_subtask_executions`

- Autenticacion: `token_required`
- Descripcion: valida si una subtask ya fue ejecutada anteriormente.
- Body: depende del contrato interno `VALIDATE_SUBTASK_EXE`.

#### `POST /ArchiveData/<token_solution>/<task>`

- Autenticacion: `API_required`
- Descripcion: endpoint interno usado por building blocks para almacenar el resultado de una tarea y registrar su metadata.
- Entrada:
  - archivo o payload multipart en la request
  - cookie opcional `metadata` con `product_name`

#### `POST /metadata/insert/<token_solution>/<task>`

- Autenticacion: `API_required`
- Descripcion: inserta metadata de un producto sin subir el archivo.
- Entrada: cookie opcional `metadata` con `product_name`.

#### `GET /metadata/get/<token_solution>`

- Autenticacion: no requerida actualmente
- Descripcion: recupera todos los metadatos de productos de una solucion y genera `list_products.csv` en resultados.

#### `GET /locate/<RN>/<task>`

- Autenticacion: no requerida
- Descripcion: endpoint marcado como deprecated. Si hay almacenamiento remoto, devuelve la ubicacion del recurso asociado a la tarea.

### Recuperacion y administracion de soluciones

#### `POST /solution/store`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: guarda una solucion en la memoria distribuida para reutilizarla o listarla despues.
- Body esperado:

```json
{
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  },
  "metadata": {
    "name": "Mi solucion",
    "desc": "Descripcion",
    "frontend": {}
  },
  "DAG": "<json_string>"
}
```

- Respuesta: incluye `info.token_solution`.

#### `POST /solution/retrieve`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: recupera una solucion almacenada.
- Body esperado:

```json
{
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  },
  "token_solution": "<token_solution>"
}
```

#### `POST /solution/delete`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: elimina una solucion de la memoria distribuida y borra su carpeta local de resultados si existe.
- Body esperado: mismo formato que `solution/retrieve`.

#### `POST /solution/list`

- Autenticacion: `token_required` + `resource_autorization_requiered`
- Descripcion: lista las soluciones del usuario. Puede recibir un filtro opcional en `params`.
- Body esperado:

```json
{
  "auth": {
    "user": "<token_user>",
    "workspace": "Default"
  },
  "params": {}
}
```

### Workspaces y datasets del usuario

#### `GET /workspace/create/<tokenuser>/<workspace>`

- Autenticacion: `token_required`
- Descripcion: crea el workspace del usuario si no existe.

#### `GET /workspace/delete/<tokenuser>/<workspace>`

- Autenticacion: `token_required`
- Descripcion: elimina un workspace completo.

#### `GET /workspace/list/<tokenuser>`

- Autenticacion: `token_required`
- Descripcion: lista todos los workspaces del usuario.

#### `GET /workspace/list/<tokenuser>/<workspace>`

- Autenticacion: `token_required`
- Descripcion: lista el contenido detallado de un workspace.

#### `GET /workspace/getfile/<tokenuser>/<workspace>/<filename>`

- Autenticacion: `token_required`
- Descripcion: descarga un archivo almacenado en el workspace del usuario.

#### `GET /workspace/delete/<tokenuser>/<workspace>/<filename>`

- Autenticacion: `token_required`
- Descripcion: elimina un archivo del workspace y su descriptor `.json` asociado si existe.

#### `POST /UploadDataset`

- Autenticacion: `token_required`
- Descripcion: sube un dataset al workspace del usuario.
- Form data esperado:
  - `file`: archivo a subir.
  - `workspace`: nombre del workspace.
  - `user`: token del usuario.

#### `POST /CreatePackage`

- Autenticacion: `token_required`
- Descripcion: empaqueta varios archivos del usuario en un `.zip` dentro de un workspace destino.
- Body esperado:

```json
{
  "tokenuser": "<token_user>",
  "name_package": "fusion_AandB",
  "list_files": [
    "WorkspaceA/uno.csv",
    "WorkspaceB/dos.csv"
  ],
  "destination": "Default",
  "force_cration": true
}
```

### Acceso a archivos y consulta de datos

#### `POST /getfile`

- Autenticacion: `token_required` + `data_autorization_requiered`
- Descripcion: descarga un archivo de entrada o un producto generado, usando una referencia abstracta por tipo.
- Body esperado:

```json
{
  "type": "LAKE",
  "data": {
    "token_user": "<token_user>",
    "catalog": "Default",
    "filename": "dataset.csv"
  }
}
```

Tambien admite referencias de tipo `SOLUTION`.

#### `POST /DatasetQuery`

- Autenticacion: `token_required` + `data_autorization_requiered`
- Descripcion: ejecuta consultas simples sobre un dataset CSV.
- Body esperado:

```json
{
  "type": "LAKE",
  "data": {
    "token_user": "<token_user>",
    "catalog": "Default",
    "filename": "dataset.csv"
  },
  "ask": [
    {
      "request": "unique",
      "value": "columna"
    }
  ]
}
```

- Tipos de consulta documentados en el codigo: `unique`, `query`, `inside`.

#### `POST /DescribeDataset/v2`

- Autenticacion: `token_required` + `data_autorization_requiered`
- Descripcion: genera una descripcion estructurada de un dataset o paquete `.zip`. Si ya existe un descriptor y no se fuerza, reutiliza el cache.
- Body esperado:

```json
{
  "type": "LAKE",
  "data": {
    "token_user": "<token_user>",
    "catalog": "Default",
    "filename": "dataset.csv"
  },
  "delimiter": ",",
  "force": false
}
```

- Extensiones soportadas directamente: `csv`, `json`, `zip`.

### Referencias y logs

#### `POST /reference/get`

- Autenticacion: no requerida
- Descripcion: resuelve un valor de referencia a partir de una tabla configurada en `referencesIV.json` y variables de entorno de consulta.
- Body esperado:

```json
{
  "query": "nombre_tabla",
  "ENV": {
    "VAR": "valor"
  }
}
```

#### `GET /getlog/<RN>`

- Autenticacion: `token_required`
- Descripcion: descarga el archivo de log asociado a una solucion.

## Codigos de respuesta frecuentes

- `200`: operacion exitosa.
- `202`: ejecucion aceptada y disparada en segundo plano.
- `401`: token faltante, invalido o expirado.
- `403`: el token no corresponde al recurso solicitado.
- `404`: recurso o solucion no encontrados.
- `406`: dataset no encontrado o no accesible.
- `503`: la memoria distribuida no acepto la operacion.

## Observaciones de implementacion

- El valor de `DAG` se espera como string JSON, no como objeto anidado directo.
- Algunas rutas administrativas usan `GET` para operaciones destructivas, por compatibilidad con la implementacion actual.
- `POST /exec` y `GET /stopDAG/...` requieren revision si se quiere un contrato HTTP consistente, porque su implementacion actual es parcial.
- La API del coordinador depende de servicios auxiliares, especialmente `auth`, Paxos y el creador de servicios cuando `MODE=SERVERLESS`.