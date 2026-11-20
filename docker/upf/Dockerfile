FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 ca-certificates iproute2 iptables curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY upf/src /app/src
COPY upf/config /app/config
EXPOSE 2152/udp 2123/udp 8805/udp 8805/tcp 42000/udp 42001/tcp 42010/tcp 42500/udp 42050/tcp
CMD ["python3", "/app/src/upf_server.py"]
