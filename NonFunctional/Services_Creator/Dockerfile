FROM ubuntu:22.04

WORKDIR /home/app/

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    python3 \
    python3-pip \
    python3-dev

ADD ./app/requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

RUN pip3 install plotly==5.3.1
RUN pip3 install -U kaleido
RUN pip3 install Flask-Cors
RUN pip3 install psutil
RUN pip3 install waitress==1.0.1

ADD ./app .

WORKDIR /home/app/puzzlemesh

RUN cmake . && make

WORKDIR /home/app

EXPOSE 5000

CMD ["python3", "app.py"]


