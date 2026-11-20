FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    mysql-connector-python==8.1.0 \
    redis==5.0.1

COPY ./camel/src/ /app/src/

EXPOSE 2906/tcp
EXPOSE 2906/sctp
CMD ["python", "/app/src/camel_engine.py"]