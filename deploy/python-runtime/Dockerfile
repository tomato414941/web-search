ARG APPLICATION_IMAGE
FROM python:3.11.18-slim-trixie@sha256:6d10e720318bd84cc3d88af92bb5a47189222e17620a2fd214da6445e4afb679 AS interpreter

FROM ${APPLICATION_IMAGE}
ARG APPLICATION_IMAGE
ARG APPLICATION_COMMIT

USER root
COPY --from=interpreter /etc/os-release /tmp/interpreter-os-release
RUN . /etc/os-release && test "$ID:$VERSION_ID" = "debian:13" \
    && . /tmp/interpreter-os-release && test "$ID:$VERSION_ID" = "debian:13" \
    && rm /tmp/interpreter-os-release \
    && rm -rf /usr/local
COPY --from=interpreter /usr/local /usr/local

ENV PYTHON_VERSION=3.11.18 \
    PYTHON_SHA256=9120e0a653868f6e3698d36cdd99e5a58903ec9469e448f21d98f7b16d8fa290 \
    AWS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

ADD --checksum=sha256:fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70 https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl /tmp/wheels/pip-26.2.2-py3-none-any.whl
ADD --checksum=sha256:42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b https://files.pythonhosted.org/packages/c4/51/29046e48f693c54e5b7412216d447a1d8362c9653148d98c02cdf65fa733/certifi-2026.10.19-py3-none-any.whl /tmp/wheels/certifi-2026.10.19-py3-none-any.whl

COPY update_ca_bundles.py /tmp/update_ca_bundles.py
RUN ldconfig \
    && /usr/local/bin/python3 /tmp/update_ca_bundles.py \
    && update-ca-certificates --fresh \
    && /usr/local/bin/python3 -m pip install --no-compile --no-cache-dir --no-deps --no-index --find-links=/tmp/wheels pip==26.2.2 \
    && if /app/.venv/bin/python -c "from importlib.util import find_spec; import sys; sys.exit(0 if find_spec('certifi') else 1)"; then \
         /usr/local/bin/python3 -m pip --python /app/.venv install --no-compile --no-cache-dir --no-deps --no-index --find-links=/tmp/wheels certifi==2026.10.19; \
       fi \
    && /app/.venv/bin/python -c "import ssl, sys; assert sys.version_info[:3] == (3, 11, 18); ssl.create_default_context()" \
    && rm /tmp/update_ca_bundles.py \
    && rm -rf /tmp/wheels

LABEL org.opencontainers.image.base.name="${APPLICATION_IMAGE}" \
      org.opencontainers.image.application.revision="${APPLICATION_COMMIT}" \
      org.opencontainers.image.python.version="3.11.18"

USER appuser
