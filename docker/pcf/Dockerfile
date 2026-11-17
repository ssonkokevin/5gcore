FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    fastapi==0.103.1 uvicorn==0.23.2 \
    pydantic==2.5.0 pydantic-settings==2.1.0 \
    pyyaml==6.0.1 python-dotenv==1.0.0
COPY pcf/src /app/src
COPY pcf/config /app/config
EXPOSE 7777/tcp 3868/tcp 3869/tcp
CMD ["python", "/app/src/pcf_server.py"]
