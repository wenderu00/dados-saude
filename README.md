# Guia de Execução - Projeto de Análise do Parque de Equipamentos

Este guia descreve como configurar e executar o script `script_carregamento_dados.py` para processar e analisar os dados do parque de equipamentos do HC-UFPE.

## 1. Estrutura de Arquivos

Para que o script funcione corretamente, os arquivos de dados (planilhas) devem estar localizados dentro de um diretório chamado `planilhas`, seguindo a estrutura abaixo:

```
.
├── script_carregamento_dados.py
├── planilhas/
│   ├── Corretivas_Externas_2018_a_2024.csv
│   ├── ServicoExternoPeriodo20251113092221.csv
│   ├── Inventario_HC_UFPE.csv
│   └── Novos dados - criticidade/
│       └── planilha de equipamentos final.csv
└── README.md
```

O script gerará os seguintes arquivos de saída dentro do diretório `planilhas`:

- `dados_consolidados_finais.csv`: O arquivo final com todos os dados processados e ordenados por prioridade.
- `servicos_migrados.csv`: Um arquivo intermediário contendo as ordens de serviço unificadas.

## 2. Dependências

As seguintes bibliotecas Python são necessárias para executar o script.

- `pandas`
- `scikit-learn`

Você pode instalar todas de uma vez com o seguinte comando:

```bash
pip install pandas scikit-learn
```

## 3. Formato das Planilhas de Entrada

O script espera que as planilhas de entrada tenham colunas específicas. Abaixo estão os detalhes para cada arquivo.

### a. `Corretivas_Externas_2018_a_2024.csv` (Ordens de Serviço Antigas)

Este arquivo contém o histórico de ordens de serviço.

- **Separador:** Ponto e vírgula (`;`)
- **Colunas utilizadas:** `O.S`, `Tipo`, `Modelo`, `Marca`, `Data Início SE`, `Data Conclusão SE`, `Fornecedor`, `Custo`, `TAG`, `Patrimônio`.

### b. `ServicoExternoPeriodo20251113092221.csv` (Ordens de Serviço Recentes)

Este arquivo contém as ordens de serviço mais recentes.

- **Separador:** Ponto e vírgula (`;`)
- **Colunas utilizadas:** `O.S`, `Tipo`, `Modelo`, `Marca`, `Abertura`, `Fechamento`, `Serviço;Assistência`, `Custo`, `Identificador (Patrimônio, ID, TAG)`.

### c. `planilha de equipamentos final.csv` (Dados de Criticidade)

Contém os dados de criticidade associados aos modelos de equipamento.

- **Separador:** Ponto e vírgula (`;`)
- **Cabeçalho:** O script ignora as 5 primeiras linhas.
- **Colunas utilizadas:** `Peso`, `Tipo Equipamento`, `Modelo`, `Fornecedor`.

### d. `Inventario_HC_UFPE.csv` (Inventário Geral)

A lista mestre de todos os equipamentos do hospital.

- **Separador:** Ponto e vírgula (`;`)
- **Colunas utilizadas:** `Identificador`, `Tipo Equipamento`, `Modelo`, `Marca`, `Localização`, `Aquisição`, `Valor (R$)`.

## 4. Como Executar o Script

1.  **Prepare o ambiente:** Certifique-se de que o Python e o `pip` estão instalados em seu sistema.
2.  **Instale as dependências:** Abra um terminal no diretório do projeto e execute o comando de instalação mencionado na seção 2.
3.  **Execute o script:** No mesmo terminal, execute o seguinte comando:

    ```bash
    python script_carregamento_dados.py
    ```

4.  **Verifique a saída:** Após a execução, o terminal exibirá um resumo das análises e o arquivo `dados_consolidados_finais.csv` será criado ou atualizado no diretório `planilhas`.
