"""
ARCHIVO: C.py (Versión Centralizada)
SISTEMA: Ecosistema Xelhua
-------------------------------------------------------------------------------
NOTAS DE ARQUITECTURA (REFACCIÓN 2026):
1. CLIENTE DE RED DE BAJO NIVEL (TCP SOCKETS): Este módulo maneja la transmisión 
   física de archivos pesados y metadatos entre los nodos del clúster. 
   Se centralizó para asegurar que todos los bloques utilicen el mismo 
   protocolo de empaquetado y fragmentación (Chunking).
2. OPTIMIZACIÓN DE MEMORIA: Utiliza un buffer fijo (BUFF_SIZE) para leer y 
   enviar archivos grandes por partes, evitando desbordamientos de RAM (OOM) 
   cuando se procesan datasets masivos.
-------------------------------------------------------------------------------
"""

import socket
import sys
import pickle
import json
import requests as api # Reservado para peticiones API REST tradicionales
import logging
import tempfile
import os
import time

LOGER = logging.getLogger()

def RestRequest(ip, port, metadata, data_file=None):
    """
    Inicia una conexión de socket TCP cruda para transmitir metadatos y 
    archivos binarios pesados de forma eficiente, evadiendo las limitaciones 
    de las peticiones HTTP tradicionales.

    Protocolo de Mensajería:
    [Tamaño_Mensaje]<SEPARATOR>[Tamaño_Archivo] + [Metadatos JSON] + [Bytes del Archivo]

    Args:
        ip (str): Dirección IP del nodo de destino.
        port (int): Puerto de escucha del nodo de destino.
        metadata (dict): Diccionario con las instrucciones ('DAG', credenciales, etc.).
        data_file (file object, optional): Puntero al archivo físico a transmitir. 
                                           Si no se provee, usa un temporal vacío.

    Returns:
        dict/None: La respuesta del servidor en formato JSON si fue exitoso, 
                   o None si la conexión falló.
    """
    # Manejo seguro de archivo temporal por defecto
    if data_file is None:
        data_file = tempfile.NamedTemporaryFile()

    HEADERSIZE = 4096
    BUFF_SIZE = 81920 * 10 # Fragmentos de ~800KB para evitar cuellos de botella
    SEPARATOR = "<SEPARATOR>"
    
    # Obtener el peso total del archivo antes de enviarlo
    filesize = os.stat(data_file.name).st_size
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # 1. Establecer conexión con el nodo destino
        client.connect((ip, port))
        
        # 2. Empaquetar y enviar Metadatos (Cabecera)
        msg = pickle.dumps(json.dumps(metadata))
        header_message = f"{len(msg)}{SEPARATOR}{filesize}"
        # Se rellena el string hasta alcanzar el HEADERSIZE estricto
        msg = bytes(f'{header_message:<{HEADERSIZE}}', 'utf-8') + msg 
        client.sendall(msg) 

        # 3. Transmisión del Archivo Físico (Streaming)
        LOGER.info("FILESIZE TO SEND: %s bytes" % filesize)
        while True:
            bytes_read = data_file.read(BUFF_SIZE)
            if not bytes_read:
                LOGER.info("FILE TRANSMISSION COMPLETE.")
                break
            # sendall garantiza que se envíe el bloque completo en redes saturadas
            client.sendall(bytes_read)
            
        data_file.close()
        
        # 4. Esperar Respuesta del Servidor (Acknowledge / Resultados)
        from_server = []
        newMessage = True
        reciv_amount = 0
        
        while True:
            LOGER.debug("Waiting for server response...")
            reply = client.recv(HEADERSIZE)
            reciv_amount += len(reply)
            
            if newMessage:
                msglen = int(reply[:HEADERSIZE])
                newMessage = False
            
            from_server.append(reply)
            
            # Si ya recibimos todos los bytes que el servidor prometió enviar
            if msglen <= reciv_amount - HEADERSIZE:
                from_server = b"".join(from_server)
                # Decodificar usando el mismo Offset (HEADERSIZE)
                ans = pickle.loads(from_server[HEADERSIZE:])
                client.close()
                return json.loads(ans)

    except socket.error as exc:
        LOGER.error(f"SOCKET ERROR: Fallo de conexión hacia {ip}:{port} - {exc}")
        client.close()
        return None