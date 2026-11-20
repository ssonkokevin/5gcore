FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.32.1 \
    pydantic==2.9.2 \
    mysql-connector-python==9.1.0

COPY ./udr/src/ /app/src/
COPY ./corelib/ /app/corelib/

EXPOSE 8006/tcp
CMD ["python", "/app/src/udr_server.py"]
