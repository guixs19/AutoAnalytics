FROM python:3.10.14-slim

WORKDIR /app

# Instalar dependências do sistema (incluindo curl para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro (melhor aproveitamento do cache)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar TODO o projeto (não só backend/)
COPY . .

# Criar diretórios necessários
RUN mkdir -p backend/temp backend/outputs backend/models backend/data

# Configurar Python path
ENV PYTHONPATH=/app

# Expor porta
EXPOSE 8000

# Healthcheck para o container
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Criar usuário não-root por segurança
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Comando de start com Gunicorn + Uvicorn
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "--timeout", "120"]