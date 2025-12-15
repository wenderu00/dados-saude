# 🐳 Guia de Publicação no DockerHub

## 📦 Imagem Docker com Dados Pré-carregados

Este guia explica como criar e publicar uma imagem Docker da aplicação **Gestão de Ativos HC** já com todos os dados carregados.

## ✅ Pré-requisitos

1. **Conta no DockerHub**: https://hub.docker.com/signup
2. **Docker instalado** e rodando
3. **Dados já importados** no banco local

## 🔍 Verificar Dados

Antes de criar a imagem, verifique se os dados estão carregados:

```bash
cd dados-saude

# Verificar se o banco existe
ls -lh data/database.db

# Verificar quantidade de dados
docker exec gestao-ativos-hc python -c "
from main import Session, engine, Equipamento, OrdemServico
from sqlmodel import select
with Session(engine) as session:
    print(f'Equipamentos: {len(session.exec(select(Equipamento)).all())}')
    print(f'Ordens: {len(session.exec(select(OrdemServico)).all())}')
"
```

Saída esperada:
```
Equipamentos: 1545
Ordens: 731
```

## 🚀 Publicar no DockerHub

### Método 1: Script Automatizado (RECOMENDADO)

```bash
cd dados-saude
./build-and-push.sh
```

O script irá:
1. ✅ Verificar se o banco de dados existe
2. ✅ Solicitar seu username do DockerHub
3. ✅ Solicitar a versão (tag) da imagem
4. ✅ Fazer build da imagem
5. ✅ Fazer login no DockerHub
6. ✅ Fazer push da imagem

### Método 2: Manual

```bash
cd dados-saude

# 1. Build da imagem
docker build -f Dockerfile.production -t seuurusername/gestao-ativos-hc:v1.0.0 .

# 2. Tag como latest
docker tag seuurusername/gestao-ativos-hc:v1.0.0 seuurusername/gestao-ativos-hc:latest

# 3. Login no DockerHub
docker login

# 4. Push das imagens
docker push seuurusername/gestao-ativos-hc:v1.0.0
docker push seuurusername/gestao-ativos-hc:latest
```

## 📋 Estrutura da Imagem

A imagem `Dockerfile.production` contém:

```
/app/
├── main.py                          # API FastAPI
├── script_carregamento_dados.py     # Scripts de ETL
├── planilhas/                       # CSVs originais
│   ├── dados_consolidados_finais.csv
│   ├── servicos_migrados.csv
│   └── ...
└── data/
    └── database.db                  # ✅ BANCO JÁ POPULADO
```

## 🎯 Usando a Imagem Publicada

### Baixar e Rodar

```bash
# Pull da imagem
docker pull seuurusername/gestao-ativos-hc:latest

# Rodar container
docker run -d \
  -p 8000:8000 \
  --name gestao-ativos \
  seuurusername/gestao-ativos-hc:latest

# Verificar logs
docker logs -f gestao-ativos

# Acessar
curl http://localhost:8000/quantidade-equipamentos
```

### Docker Compose para Produção

Crie um `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  api:
    image: seuurusername/gestao-ativos-hc:latest
    container_name: gestao-ativos-prod
    ports:
      - "8000:8000"
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
```

Rodar:

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## 🔧 Atualizar a Imagem

Quando houver mudanças nos dados:

```bash
# 1. Reimportar dados no container local
curl -X POST http://localhost:8000/importar-dados-csv-consolidado

# 2. Copiar novo banco para host
docker cp gestao-ativos-hc:/app/data/database.db ./data/

# 3. Rebuild e push com nova versão
./build-and-push.sh
# Escolha uma nova versão: v1.0.1, v1.1.0, etc.
```

## 📊 Informações da Imagem

### Tamanho Aproximado
- **Base Python 3.10-slim**: ~150MB
- **Dependências**: ~50MB
- **Código + Planilhas**: ~5MB
- **Banco de dados**: ~350KB
- **Total**: ~205MB

### Dados Incluídos
- ✅ **1.545 equipamentos** com todos os campos
- ✅ **731 ordens de serviço** vinculadas
- ✅ **Criticidade calculada** (valores de 1-3)
- ✅ **Prioridades calculadas** (0-100 scale)
- ✅ **Custos externos agregados**
- ✅ **Dados consolidados** de múltiplas fontes

### Endpoints Disponíveis

```bash
# KPIs
GET /quantidade-equipamentos
GET /quantidade-em-manutencao
GET /porcentagem-mais-10-anos
GET /custo-externo-total

# Equipamentos
GET /equipamentos
GET /equipamentos/{id}
GET /top-5-substituicao
GET /setores

# Ordens de Serviço
GET /equipamentos/{id}/ordens-servico

# Budget
POST /distribuir-orcamento
```

## 🌐 Tornar Repositório Público

No DockerHub:

1. Acesse https://hub.docker.com/
2. Vá em **Repositories**
3. Clique no repositório `gestao-ativos-hc`
4. Settings > Make Public

Agora qualquer um pode usar:

```bash
docker pull seuurusername/gestao-ativos-hc:latest
```

## 🔐 Repositório Privado

Se preferir manter privado:

```bash
# Usuários precisam fazer login antes do pull
docker login
docker pull seuurusername/gestao-ativos-hc:latest
```

## 📝 Tags Recomendadas

Use versionamento semântico:

- `v1.0.0` - Versão inicial
- `v1.1.0` - Novos dados ou funcionalidades
- `v1.1.1` - Correções de bugs
- `latest` - Sempre aponta para a mais recente

Exemplo:

```bash
# Build com múltiplas tags
docker build -f Dockerfile.production \
  -t seuurusername/gestao-ativos-hc:v1.0.0 \
  -t seuurusername/gestao-ativos-hc:latest \
  .

# Push de todas
docker push seuurusername/gestao-ativos-hc:v1.0.0
docker push seuurusername/gestao-ativos-hc:latest
```

## 🚀 Deploy em Produção

### Render.com

```yaml
services:
  - type: web
    name: gestao-ativos-hc
    env: docker
    dockerfilePath: ./Dockerfile.production
    dockerContext: ./dados-saude
    autoDeploy: true
```

### Railway.app

```bash
railway up
```

### AWS ECS / Azure Container Instances

Use a imagem do DockerHub diretamente.

## 🐛 Troubleshooting

### Build falha

```bash
# Verificar se todos os arquivos existem
ls -la data/database.db
ls -la Dockerfile.production

# Limpar cache do Docker
docker system prune -a
```

### Push falha

```bash
# Fazer logout e login novamente
docker logout
docker login

# Verificar nome da imagem
docker images | grep gestao-ativos
```

### Imagem muito grande

```bash
# Ver tamanho das layers
docker history seuurusername/gestao-ativos-hc:latest

# Otimizar planilhas (opcional)
# Remover CSVs desnecessários após importação
```

## ✅ Checklist de Publicação

- [ ] Dados importados e verificados localmente
- [ ] Build da imagem funciona sem erros
- [ ] Login no DockerHub realizado
- [ ] Tag versionada aplicada
- [ ] Push para DockerHub concluído
- [ ] Tag `latest` atualizada
- [ ] Teste com `docker pull` e `docker run`
- [ ] Documentação atualizada com nome correto da imagem
- [ ] README.md com instruções de uso

## 🎉 Pronto!

Sua aplicação agora está disponível no DockerHub e pode ser deployada em qualquer ambiente com um simples:

```bash
docker run -p 8000:8000 seuurusername/gestao-ativos-hc:latest
```

**Sem necessidade de importação manual de dados!** 🚀

