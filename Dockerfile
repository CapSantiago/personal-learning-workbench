# One Linux process. Both amd64 and arm64 still require an actual build acceptance.
FROM python:3.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    PYTHONPATH=/app/src PLW_PRIVATE_SITE=1 PLW_PDF_PYTHON=/usr/local/bin/python
WORKDIR /app
COPY requirements.lock.txt requirements-server.lock.txt ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements-server.lock.txt \
    && groupadd --gid 10001 plw && useradd --uid 10001 --gid 10001 --no-create-home plw
# Explicit allowlist: a database, account file or test fixture cannot enter the image.
COPY app.py pyproject.toml ./
COPY src/plw ./src/plw
COPY assets/pdfjs ./assets/pdfjs
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY scripts/launch_private.py scripts/setup_private.py scripts/pdf_metadata.py scripts/healthcheck.py scripts/cloud_data.py ./scripts/
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD ["python", "scripts/healthcheck.py"]
CMD ["python", "scripts/launch_private.py", "--config", "/run/plw-private/account.json"]
