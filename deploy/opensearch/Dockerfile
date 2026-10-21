FROM opensearchproject/opensearch:2.19.6

USER 0
COPY blocklist /etc/pki/ca-trust/source/blocklist
COPY ca-trust.sh /tmp/ca-trust.sh
RUN sh /tmp/ca-trust.sh && rm /tmp/ca-trust.sh
USER opensearch
