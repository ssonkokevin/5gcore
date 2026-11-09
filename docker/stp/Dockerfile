FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    build-essential \
    ca-certificates \
    git \
    libtool \
    libgtp-dev \
    libpcap-dev \
    pkg-config \
    sctp-tools \
    && rm -rf /var/lib/apt/lists/*

# Clone and build osmo-stp
WORKDIR /tmp/osmo-stp
RUN git clone --depth 1 https://gerrit.osmocom.org/osmo-stp.git . \
    && autoreconf -fi \
    && ./configure --prefix=/usr \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/osmo-stp

# Config dir
RUN mkdir -p /etc/osmocom/stp

COPY ./stp/config/osmo-stp.cfg /etc/osmocom/stp/osmo-stp.cfg

EXPOSE 2905/sctp 2905/udp
CMD ["/usr/local/bin/osmo-stp", "-c", "/etc/osmocom/stp/osmo-stp.cfg"]
