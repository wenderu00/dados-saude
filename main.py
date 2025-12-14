import pandas as pd
from typing import Optional, List
from sqlmodel import Field, SQLModel, create_engine, Session, select, Relationship
from fastapi import FastAPI, HTTPException
from datetime import datetime

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS (MODELOS) ---

class Equipamento(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    identificador: str = Field(index=True, unique=True) # TAG ou Patrimônio
    modelo: Optional[str] = None
    tipo_equipamento: Optional[str] = None
    data_aquisicao: Optional[datetime] = None
    criticidade: float = Field(default=1.0) # Vindo da planilha de criticidade
    
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
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- 2. APLICAÇÃO API ---

app = FastAPI(title="Gestão de Ativos HC", description="API para cálculo de prioridade de equipamentos")

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# --- 3. ROTAS DE INGESTÃO (CARREGAR OS DADOS DO SEU CSV PARA O BANCO) ---

@app.post("/importar-dados-csv")
def importar_dados_iniciais():
    """
    Roda UMA VEZ para popular o banco usando seus scripts existentes.
    Lê os CSVs da pasta 'planilhas', processa e salva no SQLite.
    """
    # Importando as funções do SEU script original
    try:
        import script_carregamento_dados as etl
    except ImportError:
        return {"erro": "Script original não encontrado. Coloque o script_carregamento_dados.py na mesma pasta."}

    session = Session(engine)
    
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
        
        # Cria objeto
        equip = Equipamento(
            identificador=identificador,
            modelo=str(row.get('Modelo', '')),
            tipo_equipamento=str(row.get('Tipo Equipamento', '')),
            criticidade=float(row.get('Criticidade', 1.0)),
            data_aquisicao=data_aq
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
            
            os_obj = OrdemServico(
                numero_os=str(row.get('OS', 'Unknown')),
                custo=custo_float,
                equipamento_id=equip_id,
                data_abertura=pd.to_datetime(row.get('Abertura'), errors='coerce'),
                data_fechamento=pd.to_datetime(row.get('Fechamento'), errors='coerce')
            )
            session.add(os_obj)
    
    session.commit()
    return {"status": "Sucesso", "mensagem": "Dados importados do CSV para o Banco SQL"}

# --- 4. ROTA DE PROCESSAMENTO (O QUE O CARLOS PEDIU) ---

@app.post("/calcular-prioridades")
def processar_dados_do_banco():
    """
    Lê os dados DAS TABELAS (não do CSV), calcula custos e prioridades,
    e atualiza a tabela de Equipamentos.
    """
    session = Session(engine)
    
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

@app.get("/equipamentos-prioritarios")
def listar_equipamentos():
    """Retorna a lista final ordenada para o frontend/gestor"""
    session = Session(engine)
    # Select ordenado pelo Peso (descrescente)
    statement = select(Equipamento).order_by(Equipamento.peso_prioridade.desc()).limit(50)
    results = session.exec(statement).all()
    return results

@app.get("/top-5-substituicao")
def top_5_prioridade():
    """
    Retorna apenas os 5 equipamentos mais críticos (com maior peso) para substituição imediata.
    """
    session = Session(engine)
    # Seleciona Equipamento, ordena por peso (descrescente) e limita a 5
    statement = select(Equipamento).order_by(Equipamento.peso_prioridade.desc()).limit(5)
    results = session.exec(statement).all()
    
    if not results:
        return {"mensagem": "Nenhum equipamento encontrado. Você executou a rota /calcular-prioridades?"}
        
    return results

@app.get("/quantidade-equipamentos")
def contar_equipamentos():
    """
    Retorna o número total de equipamentos cadastrados no banco de dados.
    """
    session = Session(engine)
    equipamentos = session.exec(select(Equipamento)).all()
    total = len(equipamentos)
    
    return {"total_equipamentos": total}

@app.get("/quantidade-em-manutencao")
def quantidade_em_manutencao():
    """
    Retorna a quantidade de equipamentos que possuem ordens de serviço em aberto 
    (sem data de fechamento registrada).
    """
    session = Session(engine)
    
    # Seleciona os IDs dos equipamentos que têm OS onde a data_fechamento é NULA
    # Usamos .distinct() para não contar o mesmo equipamento duas vezes se ele tiver mais de uma OS aberta
    statement = select(OrdemServico.equipamento_id)\
                .where(OrdemServico.data_fechamento == None)\
                .distinct()
                
    resultados = session.exec(statement).all()
    
    return {"quantidade_em_manutencao": len(resultados)}
@app.get("/porcentagem-mais-10-anos")
def porcentagem_obsolescencia():
    """
    Calcula e retorna a porcentagem de equipamentos que possuem 10 anos ou mais de uso.
    """
    session = Session(engine)
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
def custo_total_geral():
    """
    Retorna a soma total de todos os custos registrados nas Ordens de Serviço.
    """
    session = Session(engine)
    
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