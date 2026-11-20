FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Diameter/SCTP
RUN apt-get update && apt-get install -y \
    libsctp-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    redis==5.0.1 \
    aiofiles==23.2.1 \
    python-dotenv==1.0.0 \
    asyncio-diameter==0.3.0 \
    aiomysql==0.1.1 \
    pyyaml==6.0.1

# Install Open5GS DRA (via pip from GitHub or local build)
# For now, using our custom dra_engine.py that implements Diameter routing per RFC 3588/6733
# and integrates with MariaDB for peer/route config

COPY ./dra/src/ /app/src/
COPY ./dra/config/ /app/config/

EXPOSE 3868/tcp 3868/sctp
CMD ["python", "/app/src/dra_engine.py"]
