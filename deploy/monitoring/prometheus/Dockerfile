FROM debian:bookworm-slim AS certificates
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && sed -i -E '/^mozilla\/(Comodo_AAA_Services_root|emSign_(ECC_Root_CA|Root_TLS_CA|Root_CS_CA)_-_G3)\.crt$/s/^/!/' /etc/ca-certificates.conf \
    && update-ca-certificates && rm -rf /var/lib/apt/lists/*

FROM prom/prometheus:v3.2.1

COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

COPY config.yml /etc/prometheus/config.yml
COPY alerts.yml /etc/prometheus/alerts.yml
