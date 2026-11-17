FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    mysql-connector-python==8.1.0

COPY ./map_sccp/src/ /app/src/

EXPOSE 2905/tcp
EXPOSE 2905/udp
EXPOSE 2905/sctp
CMD ["python", "/app/src/map_sccp_server.py"]