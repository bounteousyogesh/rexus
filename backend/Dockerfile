# syntax=docker/dockerfile:1
 
FROM python:3.13-slim AS builder
 
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
 
WORKDIR /app/backend
COPY . .                            
 
COPY requirements.txt .
 
RUN python -m venv /opt/venv \
      && /opt/venv/bin/pip install --upgrade pip \                                                                                                                 
      && /opt/venv/bin/pip install -r requirements.txt \    
      && /opt/venv/bin/python -m spacy download en_core_web_sm
 
FROM python:3.13-slim AS runtime
 
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
 
WORKDIR /app/backend
COPY . .                            

# Install AWS CLI + jq
RUN apk add --no-cache python3 py3-pip jq \
    && pip install --no-cache-dir awscli
 
COPY --from=builder /opt/venv /opt/venv
COPY . .
 
RUN chmod +x /start.sh
 
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
 
USER appuser
 
EXPOSE 8000
 
# Use start script instead of direct npm command
CMD ["/start.sh"]