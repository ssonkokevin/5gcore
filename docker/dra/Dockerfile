FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    redis==5.0.1 \
    asyncio-diameter==0.3.0 \
    aiofiles==23.2.1 \
    python-dotenv==1.0.0

COPY ./dra/src/ /app/src/
COPY ./dra/config/ /app/config/

EXPOSE 3868/tcp 3868/udp
CMD ["python", "/app/src/dra_engine.py"]
