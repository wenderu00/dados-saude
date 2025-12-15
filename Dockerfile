# Usa uma imagem leve do Python
FROM python:3.10-slim

# Define a pasta de trabalho dentro do container
WORKDIR /app

# Copia os requisitos e instala (para aproveitar o cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código fonte e os scripts
COPY main.py .
COPY script_carregamento_dados.py .

# Copia a pasta de planilhas para dentro do container (incluindo subdiretórios)
# IMPORTANTE: A pasta 'planilhas' deve existir junto com o Dockerfile
COPY planilhas ./planilhas

# Cria o diretório para o banco de dados com permissões corretas
RUN mkdir -p /app/data && chmod 777 /app/data

# Expõe a porta 8000 (padrão do FastAPI)
EXPOSE 8000

# Comando para iniciar o servidor automaticamente ao rodar o container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]