FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi==0.103.1 uvicorn==0.23.2 \
    pydantic==2.5.0 pyyaml==6.0.1 redis==5.0.1
COPY nrf/src /app/src
COPY nrf/config /app/config
EXPOSE 8000/tcp
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"
CMD ["python", "/app/src/nrf_server.py"]
