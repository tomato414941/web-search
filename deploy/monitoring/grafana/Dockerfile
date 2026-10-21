FROM grafana/grafana:11.5.2

USER 0
RUN sed -i -E '/^mozilla\/(Comodo_AAA_Services_root|emSign_(ECC_Root_CA|Root_TLS_CA|Root_CS_CA)_-_G3)\.crt$/s/^/!/' /etc/ca-certificates.conf \
    && update-ca-certificates

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/grafana/dashboards

RUN chown -R 472:0 /etc/grafana/provisioning /etc/grafana/dashboards

USER 472
