FROM python:3.8-slim-bullseye

WORKDIR /home/

RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt --user 
#requierments for the app:
RUN pip install scikit-learn==1.0.2

COPY ./app app
WORKDIR /home/app

ENTRYPOINT ["python"]
CMD ["S.py"]
