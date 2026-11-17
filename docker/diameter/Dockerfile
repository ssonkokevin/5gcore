FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    mysql-connector-python==8.1.0

COPY ./diameter/src/ /app/src/

EXPOSE 3868/tcp
EXPOSE 3868/sctp
CMD ["python", "/app/src/diameter_server.py"]