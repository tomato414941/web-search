FROM grafana/grafana:11.5.2

USER 0

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/grafana/dashboards

RUN chown -R 472:0 /etc/grafana/provisioning /etc/grafana/dashboards

USER 472
