# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

WORKDIR /app

# git is required for pip to fetch wcgrid from its GitHub URL.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# wcgrid is a private GitHub repo. Cloud Build injects a fine-grained
# PAT via BuildKit's --mount=type=secret so the token never lands in
# any image layer; the global git url.insteadOf rewrite is scoped to
# this RUN step (we delete /root/.gitconfig after install).
COPY requirements.txt .
RUN --mount=type=secret,id=github_token \
    if [ -f /run/secrets/github_token ]; then \
        TOKEN=$(cat /run/secrets/github_token) && \
        git config --global url."https://${TOKEN}@github.com/".insteadOf "https://github.com/" ; \
    fi && \
    pip install --no-cache-dir -r requirements.txt gunicorn && \
    rm -f /root/.gitconfig

COPY . .

# Cloud Run sets PORT (usually 8080). Local/docker-compose often omits it → default 8000.
ENV PORT=8000
EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT}"]
