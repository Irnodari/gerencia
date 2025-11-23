FROM python:3.9-slim

WORKDIR /app

# Instala utilitários de rede E o dos2unix (Salva vidas no Windows)
RUN apt-get update && \
    apt-get install -y iputils-ping procps dos2unix && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Copia os scripts
COPY gerente.py .
COPY coletor.py .
COPY entrypoint_app.sh .

# 1. Converte quebras de linha Windows -> Linux
# 2. Dá permissão de execução
RUN dos2unix entrypoint_app.sh && \
    chmod +x entrypoint_app.sh

# Executa o script
CMD ["/bin/bash", "./entrypoint_app.sh"]