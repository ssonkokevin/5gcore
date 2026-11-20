FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for MAP/CAMEL location services
RUN apt-get update && apt-get install -y \
    libsctp-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    redis==5.0.1 \
    aiofiles==23.2.1 \
    python-dotenv==1.0.0 \
    aiomysql==0.1.1 \
    pyyaml==6.0.1 \
    fastapi==0.104.1 \
    uvicorn==0.24.0

COPY ./gmlc/src/ /app/src/
COPY ./gmlc/config/ /app/config/

EXPOSE 8082/tcp
CMD ["python", "/app/src/gmlc_server.py"]