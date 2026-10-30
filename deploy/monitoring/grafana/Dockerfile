FROM grafana/grafana:12.4.14@sha256:1b59d2076a5e08e0e9929a1225f37869ee7719f4a11c004fbfcfa8b772858e89

USER 0
RUN sed -i -E '/^mozilla\/(Comodo_AAA_Services_root|emSign_(ECC_Root_CA|Root_TLS_CA|Root_CS_CA)_-_G3)\.crt$/s/^/!/' /etc/ca-certificates.conf \
    && update-ca-certificates

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/grafana/dashboards

RUN chown -R 472:0 /etc/grafana/provisioning /etc/grafana/dashboards

USER 472
