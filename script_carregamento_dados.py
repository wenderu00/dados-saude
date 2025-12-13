import os
from datetime import datetime

import pandas as pd
from sklearn.preprocessing import MinMaxScaler

CAMINHO_PLANILHAS = "planilhas"

ORDEM_SERVICO_ANTIGA = os.path.join(CAMINHO_PLANILHAS, 'Corretivas_Externas_2018_a_2024.csv')
ORDEM_SERVICO_ATUAL = os.path.join(CAMINHO_PLANILHAS, 'ServicoExternoPeriodo20251113092221.csv')
EQUIPAMENTOS_CRITICIDADE = os.path.join(CAMINHO_PLANILHAS, 'Novos dados - criticidade', 'planilha de equipamentos final.csv')
INVENTARIO_HC = os.path.join(CAMINHO_PLANILHAS, 'Inventario_HC_UFPE.csv')

ARQUIVO_SAIDA_FINAL = os.path.join(CAMINHO_PLANILHAS, 'dados_consolidados_finais.csv')


# --- 2. FUNÇÕES DE PROCESSAMENTO ---

def migrar_dados_servico():
    """
    Passo 1: Migra e unifica os dados das ordens de serviço antigas e recentes
    para um novo formato em um único DataFrame.
    """
    print("Passo 1: Migrando dados de ordens de serviço...")
    try:
        df_contrato_sl = pd.read_csv(ORDEM_SERVICO_ANTIGA, sep=';', skiprows=[0], engine='python')
        df_recente = pd.read_csv(ORDEM_SERVICO_ATUAL, sep=';', engine='python')
    except FileNotFoundError as e:
        print(f"Erro no Passo 1: Arquivo não encontrado - {e.filename}")
        return None

    df_migrado = df_recente.copy()

    mapeamento = {
        'O.S': 'OS', 'Tipo': 'Equipamento', 'Modelo': 'Modelo', 'Marca': 'Fabricante',
        'Data Início SE': 'Abertura', 'Data Conclusão SE': 'Fechamento',
        'Fornecedor': 'Serviço;Assistência', 'Custo': 'Custo'
    }

    novas_linhas = []
    for _, row in df_contrato_sl.iterrows():
        nova_linha = {col: None for col in df_migrado.columns}
        for col_recente, col_sl in mapeamento.items():
            if col_sl in row:
                nova_linha[col_recente] = row[col_sl]
        
        tag = str(row['TAG']) if 'TAG' in row and pd.notna(row['TAG']) else ''
        patrimonio = str(row['Patrimônio']) if 'Patrimônio' in row and pd.notna(row['Patrimônio']) else ''
        identificador = f"{tag},{patrimonio}" if tag and patrimonio else tag or patrimonio
        nova_linha['Identificador (Patrimônio, ID, TAG)'] = identificador
        novas_linhas.append(nova_linha)

    if novas_linhas:
        df_migrado = pd.concat([df_migrado, pd.DataFrame(novas_linhas)], ignore_index=True)
    
    print("Passo 1 concluído com sucesso.")
    return df_migrado

def processar_criticidade():
    """
    Passo 2: Gera um DataFrame de criticidade por equipamento, baseado na 
    planilha de equipamento final.
    """
    print("Passo 2: Processando criticidade dos equipamentos...")
    try:
        df = pd.read_csv(EQUIPAMENTOS_CRITICIDADE, sep=';', header=5, encoding='utf-8')
        colunas_desejadas = ['Peso', 'Tipo Equipamento', 'Modelo', 'Fornecedor']
        df_criticidade = df[colunas_desejadas].copy()
        df_criticidade.rename(columns={'Peso': 'Criticidade'}, inplace=True)
        # Agrupa por 'Modelo' para remover duplicatas, pegando o primeiro valor encontrado
        df_criticidade = df_criticidade.groupby('Modelo').first().reset_index()
        print("Passo 2 concluído com sucesso.")
        return df_criticidade
    except FileNotFoundError:
        print(f"Erro no Passo 2: Arquivo de criticidade não encontrado em '{EQUIPAMENTOS_CRITICIDADE}'")
        return None
    except Exception as e:
        print(f"Erro inesperado no Passo 2: {e}")
        return None

def adicionar_criticidade_ao_inventario(df_criticidade):
    """
    Passo 3: Adiciona a coluna de criticidade a um novo DataFrame, baseado na
    planilha de inventário e no DataFrame de criticidade, usando inner join.
    Também renomeia a coluna de aquisição.
    """
    if df_criticidade is None:
        print("Passo 3 ignorado: DataFrame de criticidade não foi gerado.")
        return None
        
    print("Passo 3: Adicionando criticidade ao inventário...")
    try:
        df_inventario = pd.read_csv(INVENTARIO_HC, sep=';', encoding='utf-8')
        
        # Renomeia a coluna 'Aquisição' para 'Data de Aquisição'
        if 'Aquisição' in df_inventario.columns:
            df_inventario.rename(columns={'Aquisição': 'Data de Aquisição'}, inplace=True)

        # Garante que a coluna de junção 'Modelo' seja do mesmo tipo (string) em ambos
        df_inventario['Modelo'] = df_inventario['Modelo'].astype(str).str.strip()
        df_criticidade['Modelo'] = df_criticidade['Modelo'].astype(str).str.strip()

        # Realiza a junção (merge) para adicionar a criticidade, usando INNER JOIN
        df_inventario_com_criticidade = pd.merge(
            df_inventario,
            df_criticidade[['Modelo', 'Criticidade']],
            on='Modelo',
            how='inner' # Alterado para 'inner' conforme solicitado
        )
        
        print("Passo 3 concluído com sucesso.")
        return df_inventario_com_criticidade
    except FileNotFoundError:
        print(f"Erro no Passo 3: Arquivo de inventário não encontrado em '{INVENTARIO_HC}'")
        return None

def adicionar_custo_e_dados_finais(df_inventario_com_criticidade, df_servicos_migrados):
    """
    Passo 4: Gera um DataFrame final contendo o custo externo acumulado,
    a criticidade e a data de aquisição do equipamento.
    """
    if df_inventario_com_criticidade is None or df_servicos_migrados is None:
        print("Passo 4 ignorado: DataFrames de entrada ausentes.")
        return None

    print("Passo 4: Calculando custos e consolidando dados finais...")
    df_servicos = df_servicos_migrados.copy()

    # Renomeia a coluna de identificador de forma robusta
    df_servicos.rename(columns={'Identificador (Patrimônio, ID, TAG)': 'Identificador'}, inplace=True)
    df_servicos['Identificador'] = df_servicos['Identificador'].astype(str).str.strip()

    # Limpeza da coluna 'Custo'
    df_servicos['Custo_Limpo'] = df_servicos['Custo'].astype(str).str.replace('R$', '', regex=False).str.strip()
    df_servicos['Custo_Limpo'] = df_servicos['Custo_Limpo'].str.replace('.', '', regex=False)
    df_servicos['Custo_Limpo'] = df_servicos['Custo_Limpo'].str.replace(',', '.', regex=False)
    df_servicos['Custo_Limpo'] = pd.to_numeric(df_servicos['Custo_Limpo'], errors='coerce').fillna(0)

    # Calcula o custo total por equipamento
    df_custo_agregado = df_servicos.groupby('Identificador')['Custo_Limpo'].sum().reset_index()
    df_custo_agregado.rename(columns={'Custo_Limpo': 'Custo total externo'}, inplace=True)

    # Prepara o DataFrame final para a junção
    df_final = df_inventario_com_criticidade.copy()
    df_final['Identificador'] = df_final['Identificador'].astype(str).str.strip()

    # Junta os custos ao DataFrame final
    df_final = pd.merge(
        df_final,
        df_custo_agregado,
        on='Identificador',
        how='left' # Mantém todos os equipamentos, mesmo os que não têm custo
    )
    df_final['Custo total externo'].fillna(0, inplace=True)
    df_final['Status'] = 'Em uso'

    # Seleciona e reordena as colunas finais, incluindo 'Data de Aquisição' e 'Status'
    colunas_finais = [
        'Identificador', 'Tipo Equipamento', 'Modelo', 'Marca', 'Localização', 'Criticidade',
        'Data de Aquisição', 'Status', 'Valor (R$)', 'Custo total externo', 'Peso'
    ]
    # Garante que apenas colunas existentes sejam selecionadas para evitar erros
    colunas_existentes = [col for col in colunas_finais if col in df_final.columns]
    
    print("Passo 4 concluído com sucesso.")
    return df_final[colunas_existentes]


def calcular_prioridade_e_ordenar(df):
    """
    Passo 5: Calcula a pontuação de prioridade para cada equipamento,
    adiciona a coluna 'Peso' e ordena o DataFrame.
    """
    if df is None:
        print("Passo 5 ignorado: DataFrame de entrada ausente.")
        return None

    print("Passo 5: Calculando prioridade e ordenando...")
    df_prioridade = df.copy()

    # --- Pesos dos Critérios ---
    PESO_CRITICIDADE = 0.5
    PESO_CUSTO = 0.3
    PESO_IDADE = 0.2

    # --- 1. Normalizar Criticidade ---
    # Converte para numérico, tratando possíveis erros
    df_prioridade['Criticidade_Num'] = pd.to_numeric(df_prioridade['Criticidade'], errors='coerce').fillna(0)
    # Normaliza (assumindo que o valor máximo é 3)
    df_prioridade['Criticidade_Norm'] = df_prioridade['Criticidade_Num'] / 3.0

    # --- 2. Normalizar Custo Externo ---
    scaler = MinMaxScaler()
    # Garante que a coluna seja 2D para o scaler
    custos = df_prioridade['Custo total externo'].values.reshape(-1, 1)
    df_prioridade['Custo_Norm'] = scaler.fit_transform(custos)

    # --- 3. Calcular Critério de Idade (>= 10 anos) ---
    # Converte para datetime, tratando erros
    df_prioridade['Data de Aquisição'] = pd.to_datetime(df_prioridade['Data de Aquisição'], errors='coerce')
    # Calcula a idade em anos
    anos_limite = 10
    data_limite = datetime.now() - pd.DateOffset(years=anos_limite)
    # Atribui 1 se for mais antigo que o limite, 0 caso contrário
    df_prioridade['Idade_Bin'] = (df_prioridade['Data de Aquisição'] < data_limite).astype(int)

    # --- 4. Calcular Pontuação Final (Peso) ---
    df_prioridade['Peso'] = (
        df_prioridade['Criticidade_Norm'] * PESO_CRITICIDADE +
        df_prioridade['Custo_Norm'] * PESO_CUSTO +
        df_prioridade['Idade_Bin'] * PESO_IDADE
    )

    # --- 5. Ordenar e Limpar ---
    # Ordena o DataFrame pela nova coluna 'Peso'
    df_ordenado = df_prioridade.sort_values(by='Peso', ascending=False)

    # Remove colunas auxiliares de normalização
    colunas_para_remover = ['Criticidade_Num', 'Criticidade_Norm', 'Custo_Norm', 'Idade_Bin']
    df_final_ordenado = df_ordenado.drop(columns=colunas_para_remover)
    
    print("Passo 5 concluído com sucesso.")
    return df_final_ordenado


def analisar_idade_equipamentos(df):
    """
    Passo Extra: Analisa a idade dos equipamentos, calcula percentuais
    e lista os itens em cada categoria de idade.
    """
    if df is None:
        print("\nAnálise de idade ignorada: DataFrame de entrada ausente.")
        return

    print("\n--- Análise de Idade dos Equipamentos ---")
    df_analise = df.copy()

    # Garante que a coluna de data está no formato datetime
    df_analise['Data de Aquisição'] = pd.to_datetime(df_analise['Data de Aquisição'], errors='coerce')

    # Remove linhas onde a data de aquisição não pôde ser convertida
    df_analise.dropna(subset=['Data de Aquisição'], inplace=True)

    # Calcula a idade e define o critério de 10 anos
    data_limite = datetime.now() - pd.DateOffset(years=10)
    df_analise['Mais de 10 anos'] = df_analise['Data de Aquisição'] < data_limite

    # 1. Calcular e exibir os percentuais
    total_equipamentos = len(df_analise)
    contagem_idade = df_analise['Mais de 10 anos'].value_counts()
    
    if total_equipamentos > 0:
        percentuais = (contagem_idade / total_equipamentos) * 100
        print("\n1. Percentual de Equipamentos por Idade:")
        print(f"- Com 10 anos ou mais: {contagem_idade.get(True, 0)} equipamentos ({percentuais.get(True, 0):.2f}%)")
        print(f"- Com menos de 10 anos: {contagem_idade.get(False, 0)} equipamentos ({percentuais.get(False, 0):.2f}%)")

    # 2. Agrupar e listar os itens
    print("\n2. Listagem de Equipamentos por Grupo de Idade (Amostra):")
    
    # Grupo 1: Equipamentos com 10 anos ou mais
    df_mais_de_10 = df_analise[df_analise['Mais de 10 anos']]
    print(f"\n--- Grupo: Equipamentos com 10 anos ou mais ({len(df_mais_de_10)} itens) ---")
    if not df_mais_de_10.empty:
        print(df_mais_de_10[['Identificador', 'Tipo Equipamento', 'Data de Aquisição']].head())
    else:
        print("Nenhum equipamento encontrado neste grupo.")

    # Grupo 2: Equipamentos com menos de 10 anos
    df_menos_de_10 = df_analise[~df_analise['Mais de 10 anos']]
    print(f"\n--- Grupo: Equipamentos com menos de 10 anos ({len(df_menos_de_10)} itens) ---")
    if not df_menos_de_10.empty:
        print(df_menos_de_10[['Identificador', 'Tipo Equipamento', 'Data de Aquisição']].head())
    else:
        print("Nenhum equipamento encontrado neste grupo.")
    print("\n----------------------------------------")


def exibir_total_equipamentos(df):
    """
    Passo Extra: Exibe a contagem total de equipamentos no parque.
    """
    if df is None:
        print("\nContagem total ignorada: DataFrame de entrada ausente.")
        return
    
    print(f"\n--- Total de Equipamentos no Parque ---")
    print(f"Total de equipamentos processados: {len(df)}")
    print("----------------------------------------")


def calcular_custo_externo_total(df_servicos):
    """
    Passo Extra: Calcula e exibe o custo externo total de todas as ordens de serviço.
    """
    if df_servicos is None:
        print("\nCálculo de custo total ignorado: DataFrame de serviços ausente.")
        return

    print("\n--- Custo Externo Total (Todas as Ordens de Serviço) ---")
    df_custo = df_servicos.copy()

    # Limpa a coluna 'Custo' para garantir que seja numérica
    df_custo['Custo_Limpo'] = df_custo['Custo'].astype(str).str.replace('R$', '', regex=False).str.strip()
    df_custo['Custo_Limpo'] = df_custo['Custo_Limpo'].str.replace('.', '', regex=False)
    df_custo['Custo_Limpo'] = df_custo['Custo_Limpo'].str.replace(',', '.', regex=False)
    df_custo['Custo_Limpo'] = pd.to_numeric(df_custo['Custo_Limpo'], errors='coerce').fillna(0)

    custo_total = df_custo['Custo_Limpo'].sum()

    # Formata como moeda brasileira
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
        custo_formatado = locale.currency(custo_total, grouping=True)
        print(f"Custo externo total: {custo_formatado}")
    except (ImportError, locale.Error):
        print(f"Custo externo total: R$ {custo_total:,.2f}")
    
    print("----------------------------------------------------------")


def contar_equipamentos_em_manutencao(df):
    """
    Conta e exibe a quantidade de equipamentos com status 'Em manutenção'.
    """
    if df is None:
        print("\nAnálise de equipamentos em manutenção ignorada: DataFrame ausente.")
        return

    print("\n--- Análise de Equipamentos em Manutenção ---")
    
    # Usando .str.contains() para ser flexível com variações do status.
    # O na=False trata valores NaN (nulos) como não correspondentes.
    manutencao_df = df[df['Status'].str.contains('manuten', case=False, na=False)]
    
    quantidade = len(manutencao_df)
    
    print(f"Total de equipamentos em manutenção: {quantidade}")
    print("---------------------------------------------")


def distribuir_orcamento_por_prioridade(df_ordenado, orcamento):
    """
    Passo Extra: Simula a distribuição de um orçamento para substituição
    de equipamentos com base na prioridade.
    """
    if df_ordenado is None:
        print("\nDistribuição de orçamento ignorada: DataFrame ausente.")
        return

    print("\n--- Simulação de Distribuição de Orçamento por Prioridade ---")
    
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
        orcamento_formatado = locale.currency(orcamento, grouping=True)
        print(f"Orçamento inicial: {orcamento_formatado}")
    except (ImportError, locale.Error):
        print(f"Orçamento inicial: R$ {orcamento:,.2f}")

    equipamentos_para_substituir = []
    custo_total_substituicao = 0
    orcamento_restante = orcamento

    df_simulacao = df_ordenado.copy()
    # Garante que o valor é numérico para a simulação
    df_simulacao['Valor (R$)'] = pd.to_numeric(
        df_simulacao['Valor (R$)'], errors='coerce'
    ).fillna(0)

    for _, equipamento in df_simulacao.iterrows():
        custo_equipamento = equipamento['Valor (R$)']
        if custo_equipamento > 0 and orcamento_restante >= custo_equipamento:
            equipamentos_para_substituir.append(equipamento)
            orcamento_restante -= custo_equipamento
            custo_total_substituicao += custo_equipamento

    print("\nEquipamentos selecionados para substituição (ordem de prioridade):")
    if equipamentos_para_substituir:
        df_selecionados = pd.DataFrame(equipamentos_para_substituir)
        colunas = ['Identificador', 'Tipo Equipamento', 'Peso', 'Valor (R$)']
        print(df_selecionados[colunas].to_string(index=False))
    else:
        print("Nenhum equipamento selecionado com o orçamento disponível.")

    print("\nResumo da Simulação:")
    try:
        custo_total_formatado = locale.currency(
            custo_total_substituicao, grouping=True
        )
        restante_formatado = locale.currency(orcamento_restante, grouping=True)
        print(f"- Custo total da substituição: {custo_total_formatado}")
        print(f"- Orçamento restante: {restante_formatado}")
    except (ImportError, locale.Error):
        print(f"- Custo total: R$ {custo_total_substituicao:,.2f}")
        print(f"- Orçamento restante: R$ {orcamento_restante:,.2f}")
    
    print("-------------------------------------------------------------")


# --- 3. EXECUÇÃO PRINCIPAL ---

def main():
    """
    Orquestra a execução de todos os passos para processar e analisar os dados.
    """
    print("--- Iniciando script de carregamento e processamento de dados ---")
    
    # Etapa 1
    df_servicos_migrados = migrar_dados_servico()
    if df_servicos_migrados is None:
        return  # Interrompe se a migração falhar
    
    # Salva o dataframe de serviços migrados para ser usado pela API
    caminho_servicos = os.path.join(CAMINHO_PLANILHAS, 'servicos_migrados.csv')
    df_servicos_migrados.to_csv(caminho_servicos, sep=';', index=False, encoding='utf-8-sig')
    print(f"Arquivo de ordens de serviço salvo em: {caminho_servicos}")

    # Etapa 2
    df_criticidade = processar_criticidade()
    if df_criticidade is None:
        return

    # Etapa 3
    df_inventario_com_criticidade = adicionar_criticidade_ao_inventario(
        df_criticidade
    )
    if df_inventario_com_criticidade is None:
        return

    # Etapa 4
    df_final = adicionar_custo_e_dados_finais(
        df_inventario_com_criticidade, df_servicos_migrados
    )
    if df_final is None:
        return

    # --- Início da Seção de Análise ---
    exibir_total_equipamentos(df_final)
    calcular_custo_externo_total(df_servicos_migrados)
    analisar_idade_equipamentos(df_final)
    contar_equipamentos_em_manutencao(df_final)  # Nova análise adicionada
    # --- Fim da Seção de Análise ---

    # Etapa 5: Ordenação por prioridade
    df_ordenado = calcular_prioridade_e_ordenar(df_final)

    # Etapa Extra: Simulação de Orçamento
    if df_ordenado is not None:
        distribuir_orcamento_por_prioridade(df_ordenado, orcamento=1000000)

    # Salva o resultado final se o DataFrame foi gerado
    if df_ordenado is not None:
        try:
            df_ordenado.to_csv(
                ARQUIVO_SAIDA_FINAL, sep=';', index=False, encoding='utf-8-sig'
            )
            print("\n--- Processo finalizado com sucesso! ---")
            print(
                f"Planilha consolidada salva em: {ARQUIVO_SAIDA_FINAL}"
            )
            print(f"Total de equipamentos no arquivo final: {len(df_ordenado)}")
            
            # Mostra uma amostra dos dados finais
            print("\nAmostra dos dados finais (ordenados por prioridade):")
            print(df_ordenado.head().to_string())

        except Exception as e:
            print(f"\nErro ao salvar o arquivo final: {e}")
    else:
        print("\n--- Processo com erros. Nenhum arquivo foi gerado. ---")


if __name__ == "__main__":
    main()
