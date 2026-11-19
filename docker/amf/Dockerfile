FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.103.1 \
    uvicorn==0.23.2 \
    pydantic==2.5.0 \
    pyyaml==6.0.1

COPY ./corelib/ /app/corelib/
COPY ./amf/src/ /app/src/

EXPOSE 8001/tcp
CMD ["python", "/app/src/amf_server.py"]
