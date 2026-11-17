# MongoDB en Xelhua

Este documento describe en detalle como Xelhua usa MongoDB: arquitectura, modelo de datos, convenciones de colecciones, flujos de escritura/lectura y consultas utiles.

## 1. Contexto y arquitectura

MongoDB se levanta en el servicio Docker `sdb` con imagen `mongo:4.4`.

- Servicio: `sdb`
- Puerto expuesto (dev): `27017:27017`
- Base inicial: `xelhua`
- Variable de conexion en servicios: `DATABASE_HOST` (usualmente `sdb`)

El acceso desde Python se centraliza en `Handler` (archivo `NonFunctional/Paxos/app/db_handler.py`), que encapsula operaciones CRUD y trabaja con una base configurable por parametro (`db`), por defecto `xelhua`.

## 2. Convenciones de nombres

Xelhua usa naming dinamico para aislar informacion por usuario y por solucion:

- Base `xelhua`:
  - Coleccion por usuario: `<token_user>`
- Base `xelhua_bucket`:
  - Coleccion de productos por solucion: `<token_solution>`
  - Coleccion de subDAG por solucion: `subdag_<token_solution>`
  - Coleccion de subtareas por solucion: `subtask_<token_solution>`
- Base `xel_pub_sub`:
  - Coleccion fija: `Published`

En resumen, la particion principal de datos se hace por nombre de coleccion, no por campo `tenant_id`.

## 3. Mapa de bases y colecciones

### 3.1 Base `xelhua`

Rol: estado principal de soluciones (pipeline, metadata, task_list, status).

Colecciones:

- `<token_user>`

Un documento representa una solucion (`token_solution`) de ese usuario.

#### Esquema esperado de documento en `<token_user>`

| Campo              | Tipo        | Fuente                   | Descripcion               |
| ------------------ | ----------- | ------------------------ | ------------------------- |
| `token_solution` | string      | `UpdateDAGInDB`        | Identificador de solucion |
| `last_update`    | string      | `GetCurrentTimeAction` | Ultima actualizacion      |
| `DAG`            | string JSON | `prepare_dag_for_db`   | Grafo serializado         |
| `metadata`       | object      | payload de API           | Metadatos de la solucion  |
| `status`         | string      | memoria/parametro        | Estado global de solucion |
| `task_list`      | object      | memoria/parametro        | Estado por tarea          |

Ejemplo realista:

```json
{
  "token_solution": "sol_20260509_001",
  "last_update": "2026-05-09 12:44:10",
  "DAG": "[{\"id\":\"bb_filter\",\"service\":\"FilterColumn\",\"params\":{},\"children\":[]}]",
  "metadata": {
    "name": "Pipeline demo",
    "desc": "Flujo ETL",
    "tags": ["demo", "etl"],
    "frontend": {
      "layout": "default"
    }
  },
  "status": "RUNNING",
  "task_list": {
    "bb_filter": {
      "historic": [
        {
          "status": "STARTING",
          "message": "NEW SERVICE ADDED.. STARTING EXECUTION.",
          "timestamp": "2026-05-09 12:40:00"
        }
      ],
      "parent": "",
      "fingerprint": "abc123",
      "is_recovered": false,
      "data_type": "",
      "label": "",
      "index": "",
      "status": "FINISHED",
      "message": "Task finished",
      "last_update": "2026-05-09 12:44:10",
      "products_fingerprint": {
        "input": [],
        "output": ["p1"]
      },
      "timestamp": 1778323456.12
    }
  }
}
```

Observaciones:

- `DAG` se persiste como string JSON, no como arreglo BSON.
- `subtask_list` se reconstruye desde `xelhua_bucket` al recuperar solucion.

### 3.2 Base `xelhua_bucket`

Rol: almacenamiento auxiliar por solucion (subgrafos, subtareas y productos).

#### Coleccion `subdag_<token_solution>`

Uso:

- Escritura en `InsertSubdag`.
- Lectura en `GetSubdag`.
- Upsert logico via `Update_document(..., query={"id": task})`.

Ejemplo de documento:

```json
{
  "id": "bb_map_1",
  "service": "AdvancedMaps",
  "params": {
    "source": "dataset.csv"
  },
  "children": [
    {
      "id": "bb_stats_1",
      "service": "statistics",
      "params": {},
      "children": []
    }
  ]
}
```

#### Coleccion `subtask_<token_solution>`

Uso:

- Escritura en `InsertSubtask`.
- Upsert por `key` usando `Update_one(..., upsert=True)`.
- Lectura completa en `GetSubtask` y conversion a diccionario en memoria.

Ejemplo de documento:

```json
{
  "key": "taskA-subtask-1",
  "value": {
    "status": "FINISHED",
    "message": "Subtask completed",
    "parent": "taskA",
    "products_fingerprint": {
      "input": ["src1"],
      "output": ["out1"]
    }
  }
}
```

#### Coleccion `<token_solution>`

Rol: indice de productos generados por la solucion.

Uso:

- Escritura en `BucketProducts(operation="INSERT")`.
- Lectura listada en `BucketProducts(operation="GETALL")`.
- El payload se arma en `AG/app/coordinator_middleware.py` con `getMetadataFromPath`.

Campos comunes:

| Campo              | Tipo   | Descripcion                |
| ------------------ | ------ | -------------------------- |
| `id`             | string | id de tarea/producto       |
| `token_solution` | string | solucion dueña            |
| `product_name`   | string | nombre amigable            |
| `product_type`   | string | `product` o `dataview` |
| `product_kind`   | string | tipo derivado del id       |
| `product_level`  | number | nivel jerarquico           |
| `level_path`     | string | ruta de niveles            |
| `porfile`        | string | perfil/valores de nivel    |

Ejemplo:

```json
{
  "id": "bb_filter",
  "token_solution": "sol_20260509_001",
  "product_name": "dataset/product",
  "product_type": "product",
  "product_kind": "bb_filter",
  "product_level": 0,
  "level_path": "",
  "porfile": ""
}
```

### 3.3 Base `xel_pub_sub`

Rol: publicacion de soluciones.

Coleccion fija:

- `Published`

Uso:

- INSERT: genera `public_token` y guarda mapeo.
- GET: consulta por `public_token`.
- DELETE: borra por `token_solution`.

Ejemplo:

```json
{
  "public_token": "pub_9f5ad12",
  "token_user": "user_abc",
  "token_solution": "sol_20260509_001"
}
```

## 4. Flujos de datos (API -> Mongo)

### 4.1 Guardar o actualizar solucion

1. Entrada por acciones tipo `SAVE_SOLUTION` / `STORE_SOLUTION`.
2. Se construye/actualiza estructura en memoria (`BRANCHES`).
3. `UpdateDAGInDB` arma `new_solution`.
4. Se persiste en `xelhua.<token_user>` con `Update_document`.

### 4.2 Publicar solucion

1. Entrada por accion `PUBLISH`.
2. `PublishSolution` usa DB `xel_pub_sub`.
3. Inserta o consulta en `Published`.

### 4.3 Registrar productos

1. Endpoint `/ArchiveData/<token_solution>/<task>` o `/metadata/insert/...`.
2. Se construye metadata con `getMetadataFromPath(task, as_list=False)`.
3. Se añade `id`, `token_solution`, `product_name`.
4. `INSERT_PRODUCT` guarda en `xelhua_bucket.<token_solution>`.

### 4.4 Subtareas y subDAG

- `InsertSubdag` guarda en `xelhua_bucket.subdag_<token_solution>`.
- `InsertSubtask` hace upsert en `xelhua_bucket.subtask_<token_solution>`.

## 5. Consultas utiles en mongosh

Conectar:

```bash
mongosh "mongodb://localhost:27017"
```

Listar bases:

```javascript
show dbs
```

Ver soluciones de un usuario:

```javascript
use xelhua
db.getCollection("user_abc").find(
  {},
  { _id: 0, token_solution: 1, status: 1, last_update: 1 }
)
```

Ver publicadas:

```javascript
use xel_pub_sub
db.Published.find({}, { _id: 0 })
```

Ver productos de una solucion:

```javascript
use xelhua_bucket
db.getCollection("sol_20260509_001").find({}, { _id: 0 })
```

Ver subtareas de una solucion:

```javascript
use xelhua_bucket
db.getCollection("subtask_sol_20260509_001").find({}, { _id: 0 })
```

## 6. Indices recomendados

El codigo actual no define indices explicitamente. Para mejorar rendimiento/consistencia, se recomienda:

- En cada coleccion de usuario (`xelhua.<token_user>`):
  - indice unico en `token_solution`
- En `xel_pub_sub.Published`:
  - indice unico en `public_token`
  - indice unico en `token_solution`
- En `xelhua_bucket.subtask_<token_solution>`:
  - indice unico en `key`
- En `xelhua_bucket.subdag_<token_solution>`:
  - indice unico en `id`
- En `xelhua_bucket.<token_solution>`:
  - indice en `id`

Ejemplo (una coleccion concreta):

```javascript
use xel_pub_sub
db.Published.createIndex({ public_token: 1 }, { unique: true })
db.Published.createIndex({ token_solution: 1 }, { unique: true })
```

## 7. Retencion y limpieza

Al eliminar una solucion (`DELETE_SOLUTION`) se borra:

- Documento principal en `xelhua.<token_user>`

Y despues se invoca `drop_db` con nombres `subtask_<token_solution>` y `subdag_<token_solution>`. Importante:

- Esa llamada intenta eliminar bases de datos con esos nombres, no colecciones dentro de `xelhua_bucket`.
- Si el objetivo es limpiar colecciones auxiliares, debe usarse `drop_collection` sobre `xelhua_bucket`.

## 8. Riesgos y consideraciones

- `Update_document` implementa update como delete + insert (no atomico).
- No hay validacion de esquema (JSON Schema) en Mongo.
- Las colecciones dinamicas pueden crecer mucho en numero si hay muchos usuarios/soluciones.
- `db.collection_names()` esta deprecado en versiones nuevas de PyMongo.

## 9. Referencias de codigo

- `Xel.yml` (servicio Mongo `sdb`)
- `NonFunctional/Paxos/app/db_handler.py`
- `NonFunctional/Paxos/app/Acepter.py`
- `AG/app/coordinator_middleware.py`
- `AG/app/functions.py`
