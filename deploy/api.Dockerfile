# Dynamis API: FastAPI + the physics/ML pipeline, CPU-only PyTorch.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# torch first, from the CPU wheel index: its own layer, so code changes don't re-download it.
# (the image's bundled pip is too old for that index's metadata, hence the upgrade)
RUN pip install --upgrade pip \
 && pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[ml,web]"

RUN useradd --create-home --uid 10001 dynamis
USER dynamis

ENV DYNAMIS_MODEL_PATH=/app/models/surrogate.pt \
    DYNAMIS_DEVICE=cpu \
    DYNAMIS_TRUST_PROXY=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# one worker on purpose: jobs, rate-limit buckets and the model live in process memory
CMD ["uvicorn", "dynamis.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
