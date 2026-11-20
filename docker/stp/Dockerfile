FROM debian:bookworm-slim

# Install build dependencies for osmo-stp
RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    build-essential \
    ca-certificates \
    git \
    libtool \
    libpcap-dev \
    libsctp-dev \
    pkg-config \
    sctp-tools \
    && rm -rf /var/lib/apt/lists/*

# Clone and build osmo-stp from osmocom gerrit
WORKDIR /tmp/osmo-stp
RUN git clone --depth 1 https://gerrit.osmocom.org/osmo-stp.git . \
    && autoreconf -fi \
    && ./configure --prefix=/usr \
    && make -j$(nproc) \
    && make install \
    && ldconfig \
    && rm -rf /tmp/osmo-stp

# Create config and log directories
RUN mkdir -p /etc/osmocom/stp /var/log/osmocom

# Copy production-grade osmo-stp config (environment variables substituted at runtime)
COPY ./stp/config/osmo-stp.cfg /etc/osmocom/stp/osmo-stp.cfg

EXPOSE 2905/sctp 2905/udp
CMD ["/usr/bin/osmo-stp", "-c", "/etc/osmocom/stp/osmo-stp.cfg"]
