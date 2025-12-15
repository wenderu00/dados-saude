#!/bin/bash

# Script para build e push da imagem Docker com dados populados
set -e

echo "🐳 Build e Push da Imagem Docker - Gestão de Ativos HC"
echo "=========================================================="
echo ""

# Verificar se o banco de dados existe
if [ ! -f "data/database.db" ]; then
    echo "❌ Erro: Banco de dados não encontrado em data/database.db"
    echo "Execute primeiro: curl -X POST http://localhost:8000/importar-dados-csv-consolidado"
    exit 1
fi

# Mostrar tamanho do banco
DB_SIZE=$(du -h data/database.db | cut -f1)
echo "✅ Banco de dados encontrado (${DB_SIZE})"
echo ""

# Solicitar username do DockerHub
read -p "Digite seu username do DockerHub: " DOCKER_USERNAME

if [ -z "$DOCKER_USERNAME" ]; then
    echo "❌ Username não pode ser vazio"
    exit 1
fi

# Solicitar tag/versão
read -p "Digite a versão da imagem (ex: v1.0.0, latest): " VERSION
VERSION=${VERSION:-latest}

# Nome da imagem
IMAGE_NAME="${DOCKER_USERNAME}/gestao-ativos-hc"
IMAGE_TAG="${IMAGE_NAME}:${VERSION}"

echo ""
echo "📋 Resumo:"
echo "   - Imagem: ${IMAGE_TAG}"
echo "   - Dados: 1545 equipamentos, 731 ordens de serviço"
echo "   - Tamanho do DB: ${DB_SIZE}"
echo ""

read -p "Continuar com o build e push? (s/n): " CONFIRM
if [ "$CONFIRM" != "s" ] && [ "$CONFIRM" != "S" ]; then
    echo "❌ Cancelado pelo usuário"
    exit 0
fi

echo ""
echo "🔨 1. Building imagem Docker para linux/amd64..."

# Backup do .dockerignore original
if [ -f ".dockerignore" ]; then
    cp .dockerignore .dockerignore.backup
fi

# Usar .dockerignore de produção (que permite data/)
if [ -f ".dockerignore.production" ]; then
    cp .dockerignore.production .dockerignore
fi

# Build para linux/amd64 (compatível com a maioria dos servidores)
docker buildx build --platform linux/amd64 -f Dockerfile.production -t ${IMAGE_TAG} --load .

# Restaurar .dockerignore original
if [ -f ".dockerignore.backup" ]; then
    mv .dockerignore.backup .dockerignore
fi

if [ $? -ne 0 ]; then
    echo "❌ Erro no build da imagem"
    exit 1
fi

echo ""
echo "✅ Imagem criada com sucesso!"
echo ""

# Também criar tag 'latest' se não for latest
if [ "$VERSION" != "latest" ]; then
    echo "🏷️  Criando tag 'latest'..."
    docker tag ${IMAGE_TAG} ${IMAGE_NAME}:latest
fi

echo ""
echo "🔐 2. Fazendo login no DockerHub..."
echo "   (Digite sua senha quando solicitado)"
docker login

if [ $? -ne 0 ]; then
    echo "❌ Erro no login do DockerHub"
    exit 1
fi

echo ""
echo "📤 3. Fazendo push da imagem..."
docker push ${IMAGE_TAG}

if [ $? -ne 0 ]; then
    echo "❌ Erro no push da imagem"
    exit 1
fi

# Push do latest também
if [ "$VERSION" != "latest" ]; then
    echo ""
    echo "📤 4. Fazendo push do tag 'latest'..."
    docker push ${IMAGE_NAME}:latest
fi

echo ""
echo "=========================================================="
echo "✅ Imagem publicada com sucesso!"
echo ""
echo "📋 Informações da imagem:"
echo "   Repository: ${IMAGE_NAME}"
echo "   Tags: ${VERSION}"
if [ "$VERSION" != "latest" ]; then
    echo "         latest"
fi
echo ""
echo "🚀 Para usar a imagem em outro ambiente:"
echo ""
echo "   docker pull ${IMAGE_TAG}"
echo "   docker run -d -p 8000:8000 --name gestao-ativos ${IMAGE_TAG}"
echo ""
echo "   Acesse: http://localhost:8000"
echo ""
echo "📦 A imagem já contém:"
echo "   ✓ 1.545 equipamentos"
echo "   ✓ 731 ordens de serviço"
echo "   ✓ Dados consolidados e prioridades calculadas"
echo "   ✓ Pronta para uso em produção"
echo ""
echo "=========================================================="

