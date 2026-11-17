FROM python:3.8-slim-bullseye

WORKDIR /home/

#requierments for the mesh:
RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt --user 
#requierments for the app:
RUN pip install seaborn==0.11.2 --user

COPY ./app app
WORKDIR /home/app

ENTRYPOINT ["python"]
CMD ["S.py"]
