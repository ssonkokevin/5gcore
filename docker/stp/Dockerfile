FROM debian:bookworm-slim

# Install build dependencies for osmo-stp
RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    build-essential \
    ca-certificates \
    gettext-base \
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

# Template is also bind-mounted from ./stp/config at runtime; this copy is the
# fallback for running the image without the compose volume.
COPY ./stp/config/osmo-stp.cfg.template /etc/osmocom/stp/osmo-stp.cfg.template
COPY ./docker/stp/entrypoint.sh /usr/local/bin/stp-entrypoint.sh
RUN chmod 0755 /usr/local/bin/stp-entrypoint.sh

EXPOSE 2905/sctp 2905/udp
CMD ["/usr/local/bin/stp-entrypoint.sh"]
