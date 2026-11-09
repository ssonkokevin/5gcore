FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.103.1 \
    uvicorn==0.23.2 \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    mysql-connector-python==8.1.0 \
    redis==5.0.1 \
    aiofiles==23.2.1 \
    python-dotenv==1.0.0

COPY ./udm/src/ /app/src/
COPY ./udm/config/ /app/config/

EXPOSE 8080/tcp
CMD ["python", "/app/src/udm_server.py"]
