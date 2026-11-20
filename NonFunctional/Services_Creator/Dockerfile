FROM ubuntu:22.04

WORKDIR /home/app/

# Dependencias necesarias para Python y PuzzleMesh
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    python3 \
    python3-pip \
    python3-dev \
    libcurl4-openssl-dev \
    libboost-all-dev \
    libjsoncpp-dev \
    nlohmann-json3-dev \
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Repositorio oficial de Docker para Ubuntu 22.04
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
       -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu jammy stable" \
       > /etc/apt/sources.list.d/docker.list

# Instalar cliente Docker y complemento Docker Compose
# No instala ni inicia un segundo motor Docker
RUN apt-get update && apt-get install -y \
    docker-ce-cli \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Compatibilidad con los comandos docker-compose
# utilizados por el código original de PuzzleMesh.
RUN printf '%s\n' \
    '#!/bin/sh' \
    'if [ "$1" = "--log-level" ]; then' \
    '    shift 2' \
    'fi' \
    'exec docker compose "$@"' \
    > /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose

# Dependencias Python del proyecto
COPY ./app/requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

RUN pip3 install plotly==5.3.1 \
    && pip3 install -U kaleido \
    && pip3 install Flask-Cors \
    && pip3 install psutil \
    && pip3 install waitress==1.0.1

# Copiar código de Services Creator
COPY ./app .

# Compilar PuzzleMesh
WORKDIR /home/app/puzzlemesh

RUN cmake . && make -j2

# Volver al directorio principal
WORKDIR /home/app

# Puerto configurado en conf.json
EXPOSE 2000

# Iniciar el servicio principal
CMD ["python3", "server.py"]
