import pandas as pd
import os
from typing import Optional, List
from sqlmodel import Field, SQLModel, create_engine, Session, select, Relationship
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS (MODELOS) ---

class Equipamento(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    identificador: str = Field(index=True, unique=True) # TAG ou Patrimônio
    modelo: Optional[str] = None
    tipo_equipamento: Optional[str] = None
    data_aquisicao: Optional[datetime] = None
    criticidade: float = Field(default=1.0) # Vindo da planilha de criticidade
    
    # Novos campos para integração com frontend
    fabricante: Optional[str] = None  # Marca do equipamento
    setor: Optional[str] = None  # Localização/Departamento
    status: str = Field(default="Operacional")  # Operacional, Em Manutenção, Baixado
    custo_aquisicao: float = Field(default=0.0)  # Valor inicial de compra
    
    # Campos calculados (Regra de Negócio)
    custo_total_externo: float = Field(default=0.0)
    peso_prioridade: float = Field(default=0.0)

    # Relacionamento
    ordens: List["OrdemServico"] = Relationship(back_populates="equipamento")

class OrdemServico(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    numero_os: str
    data_abertura: Optional[datetime] = None
    data_fechamento: Optional[datetime] = None
    custo: float = Field(default=0.0)
    
    # Chave Estrangeira
    equipamento_id: Optional[int] = Field(default=None, foreign_key="equipamento.id")
    equipamento: Optional[Equipamento] = Relationship(back_populates="ordens")

# Cria o arquivo do banco localmente (sqlite)
# Usa o diretório 'data' para melhor compatibilidade com Docker
os.makedirs("data", exist_ok=True)
sqlite_file_name = "data/database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

# Configure connection pool settings and enable check_same_thread for SQLite
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},  # Needed for FastAPI with SQLite
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,  # Increase pool size
    max_overflow=20  # Allow more overflow connections
)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Dependency for getting database session
def get_session():
    """
    FastAPI dependency that provides a database session.
    Automatically closes the session after the request is done.
    """
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()

# --- 2. APLICAÇÃO API ---

app = FastAPI(title="Gestão de Ativos HC", description="API para cálculo de prioridade de equipamentos")

# Configurar CORS para permitir acesso do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Frontend Next.js
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# --- 3. ROTAS DE INGESTÃO (CARREGAR OS DADOS DO SEU CSV PARA O BANCO) ---

@app.post("/importar-dados-csv-consolidado")
def importar_dados_consolidados():
    """
    Importa dados do arquivo consolidado já processado (dados_consolidados_finais.csv).
    Esta é a forma mais simples e rápida de carregar os dados.
    """
    session = Session(engine)
    try:
        # Ler arquivo consolidado
        arquivo_consolidado = "planilhas/dados_consolidados_finais.csv"
        print(f"Lendo arquivo consolidado: {arquivo_consolidado}")
        
        df_consolidado = pd.read_csv(arquivo_consolidado, sep=';', encoding='utf-8')
        print(f"Total de equipamentos no arquivo: {len(df_consolidado)}")
        
        # Ler ordens de serviço migradas (combina todas as fontes)
        arquivo_servicos = "planilhas/servicos_migrados.csv"
        df_servicos = pd.read_csv(arquivo_servicos, sep=';', encoding='utf-8')
        print(f"Total de ordens de serviço: {len(df_servicos)}")
        
        # Mapear equipamentos
        mapa_equipamentos = {}
        
        # Inserir equipamentos
        print("Inserindo equipamentos no banco...")
        for _, row in df_consolidado.iterrows():
            identificador = str(row['Identificador']).strip()
            
            # Converter data
            data_aq = pd.to_datetime(row.get('Data de Aquisição'), errors='coerce')
            if pd.isna(data_aq): data_aq = None
            
            # Extrair campos
            fabricante = str(row.get('Marca', '')) if pd.notna(row.get('Marca')) else None
            setor = str(row.get('Localização', '')) if pd.notna(row.get('Localização')) else None
            status_col = str(row.get('Status', 'Em uso')).strip()
            
            # Determinar status
            if 'baixado' in status_col.lower():
                status = "Baixado"
            elif 'manutenção' in status_col.lower() or 'manutencao' in status_col.lower():
                status = "Em Manutenção"
            else:
                status = "Operacional"
            
            # Custo aquisição
            custo_aq = 0.0
            if pd.notna(row.get('Valor (R$)')):
                try:
                    custo_aq = float(row.get('Valor (R$)'))
                except (ValueError, TypeError):
                    custo_aq = 0.0
            
            # Criticidade
            criticidade = 1.0
            if pd.notna(row.get('Criticidade')):
                try:
                    criticidade = float(row.get('Criticidade'))
                except (ValueError, TypeError):
                    criticidade = 1.0
            
            # Custo total externo (já calculado no arquivo consolidado)
            custo_total_ext = 0.0
            if pd.notna(row.get('Custo total externo')):
                try:
                    custo_total_ext = float(row.get('Custo total externo'))
                except (ValueError, TypeError):
                    custo_total_ext = 0.0
            
            # Peso de prioridade (já calculado no arquivo consolidado)
            peso_prioridade = 0.0
            if pd.notna(row.get('Peso')):
                try:
                    peso_prioridade = float(row.get('Peso'))
                except (ValueError, TypeError):
                    peso_prioridade = 0.0
            
            # Criar equipamento
            equip = Equipamento(
                identificador=identificador,
                modelo=str(row.get('Modelo', '')),
                tipo_equipamento=str(row.get('Tipo Equipamento', '')),
                criticidade=criticidade,
                data_aquisicao=data_aq,
                fabricante=fabricante,
                setor=setor,
                status=status,
                custo_aquisicao=custo_aq,
                custo_total_externo=custo_total_ext,
                peso_prioridade=peso_prioridade
            )
            
            try:
                session.add(equip)
                session.commit()
                session.refresh(equip)
                mapa_equipamentos[identificador] = equip.id
                print(f"✓ Equipamento {identificador} inserido")
            except Exception as e:
                session.rollback()
                # Tentar encontrar existente
                existing = session.exec(select(Equipamento).where(Equipamento.identificador == identificador)).first()
                if existing:
                    mapa_equipamentos[identificador] = existing.id
                    print(f"  Equipamento {identificador} já existe")
        
        # Inserir ordens de serviço
        print("\nInserindo ordens de serviço...")
        contador_os = 0
        for _, row in df_servicos.iterrows():
            identificador = str(row.get('Identificador (Patrimônio, ID, TAG)', '')).strip()
            equip_id = mapa_equipamentos.get(identificador)
            
            if equip_id:
                raw_custo = row.get('Custo')
                custo_float = 0.0
                
                if not pd.isna(raw_custo):
                    try:
                        custo_str = str(raw_custo).replace('R$', '').strip().replace('.', '').replace(',', '.')
                        if custo_str.lower() != 'nan' and custo_str != '':
                            custo_float = float(custo_str)
                    except ValueError:
                        custo_float = 0.0
                
                # Tratar datas NaN
                data_ini = pd.to_datetime(row.get('Data Início SE', row.get('Abertura')), errors='coerce')
                data_fim = pd.to_datetime(row.get('Data Conclusão SE', row.get('Fechamento')), errors='coerce')
                
                # Converter NaT (Not a Time) para None
                if pd.isna(data_ini):
                    data_ini = None
                if pd.isna(data_fim):
                    data_fim = None
                
                os_obj = OrdemServico(
                    numero_os=str(row.get('O.S', row.get('OS', 'Unknown'))),
                    custo=custo_float,
                    equipamento_id=equip_id,
                    data_abertura=data_ini,
                    data_fechamento=data_fim
                )
                session.add(os_obj)
                contador_os += 1
        
        session.commit()
        print(f"\n✅ Importação concluída!")
        print(f"   - {len(mapa_equipamentos)} equipamentos")
        print(f"   - {contador_os} ordens de serviço")
        
        return {
            "status": "Sucesso", 
            "mensagem": "Dados importados do CSV consolidado",
            "equipamentos": len(mapa_equipamentos),
            "ordens_servico": contador_os
        }
    except Exception as e:
        session.rollback()
        print(f"Erro durante importação: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao importar dados: {str(e)}")
    finally:
        session.close()

@app.post("/importar-dados-csv")
def importar_dados_iniciais():
    """
    DEPRECATED: Use /importar-dados-csv-consolidado
    
    Roda UMA VEZ para popular o banco usando seus scripts existentes.
    Lê os CSVs da pasta 'planilhas', processa e salva no SQLite.
    """
    # Importando as funções do SEU script original
    try:
        import script_carregamento_dados as etl
    except ImportError:
        return {"erro": "Script original não encontrado. Coloque o script_carregamento_dados.py na mesma pasta."}

    session = Session(engine)
    try:
        # 1. Executa a lógica de migração do seu script
        print("Gerando DataFrames usando o script original...")
        df_servicos = etl.migrar_dados_servico()
        df_criticidade = etl.processar_criticidade()
        df_inventario = etl.adicionar_criticidade_ao_inventario(df_criticidade)
        
        if df_inventario is None or df_servicos is None:
            raise HTTPException(status_code=500, detail="Erro ao ler planilhas CSV")

        # 2. Inserir Equipamentos
        print("Inserindo Equipamentos no Banco...")
        mapa_equipamentos = {} 
        
        for _, row in df_inventario.iterrows():
            identificador = str(row['Identificador']).strip()
            
            # Converte data
            data_aq = pd.to_datetime(row.get('Data de Aquisição'), errors='coerce')
            if pd.isna(data_aq): data_aq = None
            
            # Extrai novos campos
            fabricante = str(row.get('Marca', '')) if pd.notna(row.get('Marca')) else None
            setor = str(row.get('Localização', '')) if pd.notna(row.get('Localização')) else None
            
            # Determina status baseado nas colunas Baixado e Permitir O.S.
            baixado = str(row.get('Baixado', 'NÃO')).strip().upper()
            permitir_os = str(row.get('Permitir O.S.', 'SIM')).strip().upper()
            
            if baixado == 'SIM':
                status = "Baixado"
            elif permitir_os == 'NÃO':
                status = "Em Manutenção"
            else:
                status = "Operacional"
            
            # Extrai custo de aquisição
            custo_aq = 0.0
            if pd.notna(row.get('Valor (R$)')):
                try:
                    custo_aq = float(row.get('Valor (R$)'))
                except (ValueError, TypeError):
                    custo_aq = 0.0
            
            # Cria objeto
            equip = Equipamento(
                identificador=identificador,
                modelo=str(row.get('Modelo', '')),
                tipo_equipamento=str(row.get('Tipo Equipamento', '')),
                criticidade=float(row.get('Criticidade', 1.0)),
                data_aquisicao=data_aq,
                fabricante=fabricante,
                setor=setor,
                status=status,
                custo_aquisicao=custo_aq
            )
            
            try:
                session.add(equip)
                session.commit()
                session.refresh(equip)
                mapa_equipamentos[identificador] = equip.id
            except:
                session.rollback()
                existing = session.exec(select(Equipamento).where(Equipamento.identificador == identificador)).first()
                if existing:
                    mapa_equipamentos[identificador] = existing.id

        # 3. Inserir Ordens de Serviço
        print("Inserindo Ordens de Serviço no Banco...")
        for _, row in df_servicos.iterrows():
            identificador = str(row.get('Identificador (Patrimônio, ID, TAG)', '')).strip()
            equip_id = mapa_equipamentos.get(identificador)
            
            if equip_id:
                raw_custo = row.get('Custo')
                custo_float = 0.0

                # --- CORREÇÃO AQUI: Tratamento robusto para evitar NaN ---
                if not pd.isna(raw_custo):
                    try:
                        # Limpa R$, pontos de milhar e troca vírgula por ponto
                        custo_str = str(raw_custo).replace('R$', '').strip().replace('.', '').replace(',', '.')
                        if custo_str.lower() != 'nan' and custo_str != '':
                            custo_float = float(custo_str)
                    except ValueError:
                        custo_float = 0.0
                # ---------------------------------------------------------
                
                # Tratar datas NaN
                data_ini = pd.to_datetime(row.get('Data Início SE', row.get('Abertura')), errors='coerce')
                data_fim = pd.to_datetime(row.get('Data Conclusão SE', row.get('Fechamento')), errors='coerce')
                
                # Converter NaT (Not a Time) para None
                if pd.isna(data_ini):
                    data_ini = None
                if pd.isna(data_fim):
                    data_fim = None
                
                os_obj = OrdemServico(
                    numero_os=str(row.get('O.S', row.get('OS', 'Unknown'))),
                    custo=custo_float,
                    equipamento_id=equip_id,
                    data_abertura=data_ini,
                    data_fechamento=data_fim
                )
                session.add(os_obj)
        
        session.commit()
        return {"status": "Sucesso", "mensagem": "Dados importados do CSV para o Banco SQL"}
    finally:
        session.close()

# --- 4. ROTA DE PROCESSAMENTO (O QUE O CARLOS PEDIU) ---

@app.post("/calcular-prioridades")
def processar_dados_do_banco():
    """
    Lê os dados DAS TABELAS (não do CSV), calcula custos e prioridades,
    e atualiza a tabela de Equipamentos.
    """
    session = Session(engine)
    try:
        # 1. Pegar todos os equipamentos
        equipamentos = session.exec(select(Equipamento)).all()
        
        # Variáveis para normalização (Replicando lógica do passo 5 do seu script)
        max_custo = 0
        
        # Passo A: Calcular custo total de cada equipamento (Agregação via Python/SQL)
        for equip in equipamentos:
            # Soma custos das OS vinculadas a este equipamento
            custo_total = sum([os.custo for os in equip.ordens])
            equip.custo_total_externo = custo_total
            
            if custo_total > max_custo:
                max_custo = custo_total
                
        # Passo B: Calcular Score de Prioridade
        PESO_CRITICIDADE = 0.5
        PESO_CUSTO = 0.3
        PESO_IDADE = 0.2
        
        for equip in equipamentos:
            # Normalização
            crit_norm = equip.criticidade / 3.0 # Assumindo max 3
            custo_norm = (equip.custo_total_externo / max_custo) if max_custo > 0 else 0
            
            # Idade (> 10 anos)
            idade_bin = 0
            if equip.data_aquisicao:
                anos = (datetime.now() - equip.data_aquisicao).days / 365
                if anos >= 10:
                    idade_bin = 1
            
            # Fórmula final
            equip.peso_prioridade = (crit_norm * PESO_CRITICIDADE) + \
                                    (custo_norm * PESO_CUSTO) + \
                                    (idade_bin * PESO_IDADE)
            
            session.add(equip)
        
        session.commit()
        return {"status": "Processamento concluído", "total_equipamentos_atualizados": len(equipamentos)}
    finally:
        session.close()

@app.get("/equipamentos-prioritarios")
def listar_equipamentos(session: Session = Depends(get_session)):
    """Retorna a lista final ordenada para o frontend/gestor"""
    # Select ordenado pelo Peso (descrescente)
    statement = select(Equipamento).order_by(Equipamento.peso_prioridade.desc()).limit(50)
    results = session.exec(statement).all()
    return results

@app.get("/top-5-substituicao")
def top_5_prioridade(session: Session = Depends(get_session)):
    """
    Retorna apenas os 5 equipamentos mais críticos (com maior peso) para substituição imediata.
    Formato compatível com o frontend.
    """
    # Seleciona Equipamento, ordena por peso (descrescente) e limita a 5
    statement = select(Equipamento).order_by(Equipamento.peso_prioridade.desc()).limit(5)
    equipamentos = session.exec(statement).all()
    
    if not equipamentos:
        return {"mensagem": "Nenhum equipamento encontrado. Você executou a rota /calcular-prioridades?"}
    
    # Converter para formato do frontend (mesmo formato de /equipamentos)
    resultado = []
    for eq in equipamentos:
        # Coletar IDs das ordens de serviço
        ordem_ids = [os.numero_os for os in eq.ordens]
        
        resultado.append({
            "identificador": eq.identificador,
            "modelo": eq.modelo,
            "fabricante": eq.fabricante or "",
            "setor": eq.setor or "",
            "status": eq.status,
            "dataAquisicao": eq.data_aquisicao.isoformat() if eq.data_aquisicao else None,
            "custo": eq.custo_aquisicao,
            "totalCustoExterno": eq.custo_total_externo,
            "prioridadeScore": round(eq.peso_prioridade * 100, 2),  # Converter para escala 0-100
            "ordemServicoIds": ordem_ids
        })
    
    return resultado

@app.get("/quantidade-equipamentos")
def contar_equipamentos(session: Session = Depends(get_session)):
    """
    Retorna o número total de equipamentos cadastrados no banco de dados.
    """
    equipamentos = session.exec(select(Equipamento)).all()
    total = len(equipamentos)
    
    return {"total_equipamentos": total}

@app.get("/quantidade-em-manutencao")
def quantidade_em_manutencao(session: Session = Depends(get_session)):
    """
    Retorna a quantidade de equipamentos que possuem ordens de serviço em aberto 
    (sem data de fechamento registrada).
    """
    # Seleciona os IDs dos equipamentos que têm OS onde a data_fechamento é NULA
    # Usamos .distinct() para não contar o mesmo equipamento duas vezes se ele tiver mais de uma OS aberta
    statement = select(OrdemServico.equipamento_id)\
                .where(OrdemServico.data_fechamento == None)\
                .distinct()
                
    resultados = session.exec(statement).all()
    
    return {"quantidade_em_manutencao": len(resultados)}
@app.get("/porcentagem-mais-10-anos")
def porcentagem_obsolescencia(session: Session = Depends(get_session)):
    """
    Calcula e retorna a porcentagem de equipamentos que possuem 10 anos ou mais de uso.
    """
    equipamentos = session.exec(select(Equipamento)).all()
    
    total = len(equipamentos)
    
    if total == 0:
        return {
            "porcentagem": 0.0, 
            "mensagem": "Nenhum equipamento cadastrado."
        }
    
    qtd_mais_10_anos = 0
    agora = datetime.now()
    
    for equip in equipamentos:
        if equip.data_aquisicao:
            # Cálculo de diferença em dias dividido por 365
            anos_uso = (agora - equip.data_aquisicao).days / 365
            if anos_uso >= 10:
                qtd_mais_10_anos += 1
    
    porcentagem = (qtd_mais_10_anos / total) * 100
    
    return {
        "porcentagem": round(porcentagem, 2), # Arredonda para 2 casas decimais
        "quantidade_mais_10_anos": qtd_mais_10_anos,
        "total_equipamentos": total
    }

@app.get("/custo-externo-total")
def custo_total_geral(session: Session = Depends(get_session)):
    """
    Retorna a soma total de todos os custos registrados nas Ordens de Serviço.
    """
    # Busca todas as ordens de serviço
    ordens = session.exec(select(OrdemServico)).all()
    
    # Soma o campo 'custo' de cada ordem
    total = sum([os.custo for os in ordens])
    
    # Formatação básica para moeda brasileira para facilitar leitura
    total_formatado = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    return {
        "custo_total_bruto": total,
        "custo_total_formatado": total_formatado
    }

# --- NOVAS ROTAS PARA INTEGRAÇÃO COM FRONTEND ---

@app.get("/equipamentos")
def listar_equipamentos_com_filtros(
    session: Session = Depends(get_session),
    setor: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_aquisicao_inicio: Optional[str] = Query(None),
    data_aquisicao_fim: Optional[str] = Query(None),
    custo_min: Optional[float] = Query(None),
    custo_max: Optional[float] = Query(None)
):
    """
    Lista todos os equipamentos com filtros opcionais.
    Retorna os equipamentos ordenados por prioridade (peso_prioridade decrescente).
    """
    statement = select(Equipamento)
    
    # Aplicar filtros
    if setor:
        statement = statement.where(Equipamento.setor == setor)
    
    if status:
        statement = statement.where(Equipamento.status == status)
    
    if data_aquisicao_inicio:
        try:
            data_inicio = datetime.fromisoformat(data_aquisicao_inicio)
            statement = statement.where(Equipamento.data_aquisicao >= data_inicio)
        except ValueError:
            pass
    
    if data_aquisicao_fim:
        try:
            data_fim = datetime.fromisoformat(data_aquisicao_fim)
            statement = statement.where(Equipamento.data_aquisicao <= data_fim)
        except ValueError:
            pass
    
    if custo_min is not None:
        statement = statement.where(Equipamento.custo_aquisicao >= custo_min)
    
    if custo_max is not None:
        statement = statement.where(Equipamento.custo_aquisicao <= custo_max)
    
    # Ordenar por prioridade
    statement = statement.order_by(Equipamento.peso_prioridade.desc())
    
    equipamentos = session.exec(statement).all()
    
    # Converter para formato do frontend
    resultado = []
    for eq in equipamentos:
        # Coletar IDs das ordens de serviço
        ordem_ids = [os.numero_os for os in eq.ordens]
        
        resultado.append({
            "identificador": eq.identificador,
            "modelo": eq.modelo,
            "fabricante": eq.fabricante or "",
            "setor": eq.setor or "",
            "status": eq.status,
            "dataAquisicao": eq.data_aquisicao.isoformat() if eq.data_aquisicao else None,
            "custo": eq.custo_aquisicao,
            "totalCustoExterno": eq.custo_total_externo,
            "prioridadeScore": round(eq.peso_prioridade * 100, 2),  # Converter para escala 0-100
            "ordemServicoIds": ordem_ids
        })
    
    return resultado

@app.get("/equipamentos/{identificador}")
def obter_equipamento_por_id(identificador: str, session: Session = Depends(get_session)):
    """
    Retorna um equipamento específico pelo identificador.
    """
    equipamento = session.exec(
        select(Equipamento).where(Equipamento.identificador == identificador)
    ).first()
    
    if not equipamento:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    
    # Coletar IDs das ordens de serviço
    ordem_ids = [os.numero_os for os in equipamento.ordens]
    
    return {
        "identificador": equipamento.identificador,
        "modelo": equipamento.modelo,
        "fabricante": equipamento.fabricante or "",
        "setor": equipamento.setor or "",
        "status": equipamento.status,
        "dataAquisicao": equipamento.data_aquisicao.isoformat() if equipamento.data_aquisicao else None,
        "custo": equipamento.custo_aquisicao,
        "totalCustoExterno": equipamento.custo_total_externo,
        "prioridadeScore": round(equipamento.peso_prioridade * 100, 2),
        "ordemServicoIds": ordem_ids
    }

@app.get("/equipamentos/{identificador}/ordens-servico")
def obter_ordens_servico_equipamento(identificador: str, session: Session = Depends(get_session)):
    """
    Retorna todas as ordens de serviço de um equipamento específico.
    """
    # Verificar se equipamento existe
    equipamento = session.exec(
        select(Equipamento).where(Equipamento.identificador == identificador)
    ).first()
    
    if not equipamento:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    
    # Buscar ordens de serviço
    ordens = session.exec(
        select(OrdemServico)
        .where(OrdemServico.equipamento_id == equipamento.id)
        .order_by(OrdemServico.data_abertura.desc())
    ).all()
    
    # Converter para formato do frontend
    resultado = []
    for os in ordens:
        resultado.append({
            "ordemServico": os.numero_os,
            "identificadorEquipamento": identificador,
            "custo": os.custo,
            "dataInicio": os.data_abertura.isoformat() if os.data_abertura else None,
            "dataConclusao": os.data_fechamento.isoformat() if os.data_fechamento else None
        })
    
    return resultado

@app.post("/processar-dados-do-banco")
def processar_dados_do_banco(session: Session = Depends(get_session)):
    """
    Calcula custo total externo e peso de prioridade para cada equipamento
    com base nas ordens de serviço registradas.
    """
    try:
        from sklearn.preprocessing import MinMaxScaler
        
        print("Iniciando processamento dos dados...")
        
        # Buscar todos os equipamentos
        equipamentos = session.exec(select(Equipamento)).all()
        print(f"Total de equipamentos: {len(equipamentos)}")
        
        # Para cada equipamento, calcular custo total externo
        for equip in equipamentos:
            ordens = session.exec(
                select(OrdemServico).where(OrdemServico.equipamento_id == equip.id)
            ).all()
            
            custo_total = sum(os.custo for os in ordens if os.custo)
            equip.custo_total_externo = custo_total
        
        session.commit()
        print("Custos externos calculados.")
        
        # Calcular prioridade
        # Pesos dos critérios
        PESO_CRITICIDADE = 0.5
        PESO_CUSTO = 0.3
        PESO_IDADE = 0.2
        
        # Preparar dados para normalização
        custos = [equip.custo_total_externo for equip in equipamentos]
        criticidades = [equip.criticidade for equip in equipamentos]
        
        # Normalizar custos
        scaler = MinMaxScaler()
        if max(custos) > 0:
            custos_norm = scaler.fit_transform([[c] for c in custos])
        else:
            custos_norm = [[0] for _ in custos]
        
        # Normalizar criticidade (assumindo max = 3)
        criticidades_norm = [c / 3.0 for c in criticidades]
        
        # Calcular critério de idade (>= 10 anos)
        from datetime import datetime, timedelta
        data_limite = datetime.now() - timedelta(days=365*10)
        
        for i, equip in enumerate(equipamentos):
            idade_bin = 0
            if equip.data_aquisicao and equip.data_aquisicao < data_limite:
                idade_bin = 1
            
            # Calcular peso de prioridade
            peso = (
                criticidades_norm[i] * PESO_CRITICIDADE +
                custos_norm[i][0] * PESO_CUSTO +
                idade_bin * PESO_IDADE
            )
            
            equip.peso_prioridade = peso
        
        session.commit()
        print("Prioridades calculadas com sucesso.")
        
        return {
            "status": "Sucesso",
            "mensagem": "Dados processados e prioridades calculadas",
            "equipamentos_processados": len(equipamentos)
        }
    
    except Exception as e:
        session.rollback()
        print(f"Erro no processamento: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar dados: {str(e)}")

@app.get("/setores")
def listar_setores_unicos(session: Session = Depends(get_session)):
    """
    Retorna uma lista única de todos os setores cadastrados.
    """
    equipamentos = session.exec(select(Equipamento)).all()
    
    # Extrair setores únicos, filtrando None e vazios
    setores = set()
    for eq in equipamentos:
        if eq.setor and eq.setor.strip():
            setores.add(eq.setor.strip())
    
    return sorted(list(setores))

@app.post("/distribuir-orcamento")
def distribuir_orcamento_inteligente(dados: dict, session: Session = Depends(get_session)):
    """
    Distribui o orçamento disponível entre os equipamentos prioritários.
    Retorna sugestões de substituição baseadas na prioridade.
    
    Body: { "orcamento": float }
    """
    orcamento = dados.get("orcamento", 0)
    
    if orcamento <= 0:
        return {
            "suggestions": [],
            "totalConsumido": 0,
            "saldo": orcamento
        }
    
    # Buscar equipamentos ordenados por prioridade
    equipamentos = session.exec(
        select(Equipamento)
        .order_by(Equipamento.peso_prioridade.desc())
    ).all()
    
    suggestions = []
    total_consumido = 0.0
    saldo_restante = orcamento
    
    # Selecionar equipamentos que cabem no orçamento
    for eq in equipamentos:
        custo_substituicao = eq.custo_aquisicao if eq.custo_aquisicao > 0 else eq.custo_total_externo
        
        # Se o custo de substituição couber no saldo
        if custo_substituicao > 0 and custo_substituicao <= saldo_restante:
            suggestions.append({
                "identificador": f"NOVO-{eq.identificador}",  # Novo equipamento
                "modelo": eq.modelo,
                "fabricante": eq.fabricante or "",
                "setor": eq.setor or "",
                "status": "Novo",
                "custo": custo_substituicao,
                "totalCustoExterno": 0.0,
                "substituicaoEquipamentoId": eq.identificador  # Equipamento sendo substituído
            })
            
            total_consumido += custo_substituicao
            saldo_restante -= custo_substituicao
    
    return {
        "suggestions": suggestions,
        "totalConsumido": total_consumido,
        "saldo": saldo_restante
    }