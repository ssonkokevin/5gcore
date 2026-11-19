# HSS Dockerfile (TS 29.563 Nhss server + EPS-UDR access)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.32.1 \
    mysql-connector-python==9.1.0 \
    pydantic==2.9.2 \
    pycryptodome==3.20.0 \
    python-multipart==0.0.9

# Copy source and config
COPY hss/src/nhss_server.py /app/src/nhss_server.py
COPY hss/config/hss.yaml /app/config/hss.yaml
COPY ./corelib/ /app/corelib/

EXPOSE 8090

CMD ["python", "/app/src/nhss_server.py"]
