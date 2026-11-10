# The API image for the always-on Oracle VM (docs/plans/2026-11-redesign
# PLAN.md, phase P0c). Built from backend/, for linux/arm64 (the VM) and
# linux/amd64 alike:
#
#   docker buildx build --platform linux/arm64 -t f1ai-api:dev \
#     --build-arg GIT_COMMIT=$(git rev-parse HEAD) backend
#
# It carries no configuration and no secrets. Credentials come from the
# deployment's env file at run time, and .dockerignore is an allowlist of
# git-tracked code, because the image is published to a public registry.

# runtime.txt's Python, so the VM runs what Render and CI run.
FROM python:3.13.17-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# A fixed uid, so the VM can own the host directories mounted below
# (chown 10001:10001 /srv/f1ai/...). The home directory is for libraries that
# keep a per-user cache there, matplotlib's font cache among them.
RUN groupadd --system --gid 10001 f1ai \
    && useradd --system --uid 10001 --gid f1ai --create-home --home-dir /home/f1ai f1ai

WORKDIR /app

# CPU-only torch, installed before the requirements so they find it satisfied.
# PyPI's own torch wheels for aarch64 are CUDA builds: 2.15.0 pulls about 20
# nvidia-*, cuda-* and triton packages, gigabytes no Oracle A1 core can use. The
# +cpu build exists only on PyTorch's index.
#
# DEPLOYMENT.md §12 tells how this index once broke Render's build: pip then
# resolved torch's *dependencies* on PyTorch's flat index too, and a stale pip
# choked on one of them. Here --no-deps takes only torch's own wheel from that
# index; its dependencies come from PyPI in the next step.
#
# Bump TORCH_VERSION by hand: Dependabot and pip-audit only see the
# requirements files.
ARG TORCH_VERSION=2.15.0
RUN pip install --no-cache-dir --no-deps \
    --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}+cpu"

# requirements-ingest.txt includes requirements.txt and adds the local models
# (sentence-transformers) and the PDF loaders. The VM has the memory Render
# lacked, so rulebook search and chat-memory recall run in the API itself, and
# the rulebook ingest runs from this same image. `pip check` fails the build if
# the CPU torch left anything unsatisfied.
COPY requirements.txt requirements-ingest.txt ./
RUN pip install --no-cache-dir -r requirements-ingest.txt && pip check

COPY . .

# Everything the API writes at run time lives under /var/lib/f1ai, and the VM
# mounts a host directory over each one, so a redeploy keeps it:
#   f1_cache/     FastF1's HTTP cache (FASTF1_CACHE_DIR)
#   huggingface/  the embedder and reranker weights (HF_HOME)
#   f1db/         the f1db SQLite file, its .version stamp, and the .incoming
#                 staging files written while a release swaps in (F1DB_PATH)
# The code itself stays root-owned and read-only to the app.
RUN mkdir -p /var/lib/f1ai/f1_cache /var/lib/f1ai/huggingface /var/lib/f1ai/f1db \
    && chown -R f1ai:f1ai /var/lib/f1ai

ENV FASTF1_CACHE_DIR=/var/lib/f1ai/f1_cache \
    HF_HOME=/var/lib/f1ai/huggingface \
    F1DB_PATH=/var/lib/f1ai/f1db/f1db.db \
    ENABLE_LOCAL_MODELS=true

# The commit this image was built from: Sentry's release
# (app/error_tracking.py). Declared last so a new commit rebuilds only the
# layers below it, never the dependency install.
ARG GIT_COMMIT=""
ENV GIT_COMMIT=${GIT_COMMIT}

USER f1ai
EXPOSE 8000

# One worker, deliberately: the FastF1 lock, the f1db sync, the lifespan loops
# and the in-memory stores all assume a single process. Caddy terminates TLS in
# front, so uvicorn trusts its X-Forwarded-* headers. That is safe only while
# port 8000 stays off the public interface (deploy/oracle/compose.yaml, P0c.5).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
