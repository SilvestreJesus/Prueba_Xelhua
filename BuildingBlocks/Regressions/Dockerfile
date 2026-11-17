FROM python:3.8-slim-bullseye
#FROM python:3.8.6

WORKDIR /home/

#requierments for the mesh:
RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt --user 
#requierments for the app:
COPY app_requirements.txt app_requirements.txt
RUN pip install -r app_requirements.txt --user 

COPY ./app app
WORKDIR /home/app

ENTRYPOINT ["python"]
CMD ["S.py"]
