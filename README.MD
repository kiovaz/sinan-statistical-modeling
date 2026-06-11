<div align="center">

# SINAN Statistical Modeling — Zika Vírus (2018–2026)

**Extração, Modelagem Relacional, Análise Estatística e Visualização Interativa de Dados Epidemiológicos do Zika Vírus no Brasil**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)](https://scikit-learn.org)
[![Prophet](https://img.shields.io/badge/Prophet-Meta-0467DF?style=for-the-badge&logo=meta&logoColor=white)](https://facebook.github.io/prophet/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

*Sistema end-to-end que cobre desde a ingestão do arquivo bruto (CSV/DataSUS) até a disponibilização de um painel de Business Intelligence com modelos de Machine Learning embarcados.*

</div>

---

## 📋 Sumário

- [Visão Geral](#-visão-geral)
- [Arquitetura do Projeto](#-arquitetura-do-projeto)
- [Estrutura de Diretórios](#-estrutura-de-diretórios)
- [Componentes Detalhados](#-componentes-detalhados)
  - [Banco de Dados e Modelagem](#1--banco-de-dados-e-modelagem-sql)
  - [Pipeline ETL](#2--pipeline-etl-scripts)
  - [Análise Exploratória e ML](#3--análise-exploratória-e-machine-learning-notebook)
  - [Dashboard Interativo](#4--dashboard-interativo-interface)
- [Stack Tecnológica](#-stack-tecnológica)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação e Configuração](#-instalação-e-configuração)
- [Uso](#-uso)
- [Licença](#-licença)

---

## 🔍 Visão Geral

Este projeto realiza a **análise epidemiológica completa** das notificações de **Zika Vírus** no Brasil entre **2018 e 2026**, utilizando dados públicos do **SINAN (Sistema de Informação de Agravos de Notificação)** disponibilizados pelo **DataSUS**.

O sistema foi projetado para cobrir todo o ciclo de vida dos dados:

| Etapa | Descrição |
|:------|:----------|
| **Ingestão** | Leitura e parsing do CSV bruto do DataSUS |
| **Transformação** | Limpeza, deduplicação inteligente e normalização |
| **Armazenamento** | Carga em banco PostgreSQL altamente normalizado |
| **Análise** | EDA, modelagem preditiva (Prophet) e clusterização (K-Means) |
| **Visualização** | Dashboard interativo em Streamlit com 4 abas analíticas |

---

## 🏗 Arquitetura do Projeto

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FONTE DE DADOS                              │
│                   CSV Bruto (SINAN/DataSUS)                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PIPELINE ETL (scripts/)                       │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐ │
│  │  Extração &   │→│  Deduplicação    │→│  Carga Otimizada      │ │
│  │  Limpeza      │  │  Inteligente     │  │  (Batch/Chunks)      │ │
│  └──────────────┘  └──────────────────┘  └───────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   POSTGRESQL (sql/)                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │  Dimensões │  │   Fatos    │  │  Triggers  │  │    Views     │ │
│  │  (UF, Mun, │  │ (Notific., │  │ (Auditoria │  │ (Agregações  │ │
│  │  CNES, CBO)│  │  Clínico)  │  │  JSONB)    │  │  semanais)   │ │
│  └────────────┘  └────────────┘  └────────────┘  └──────────────┘ │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌──────────────────────┐  ┌──────────────────────────────────────────┐
│  NOTEBOOKS (notebook/)│  │      DASHBOARD STREAMLIT (interface/)   │
│  ┌────────────────┐  │  │  ┌────────┐ ┌────────┐ ┌─────────────┐ │
│  │  EDA           │  │  │  │Sazona- │ │Tendên- │ │  Previsão   │ │
│  │  Prophet       │  │  │  │lidade  │ │cia UF  │ │  (Prophet)  │ │
│  │  K-Means + PCA │  │  │  └────────┘ └────────┘ └─────────────┘ │
│  └────────────────┘  │  │  ┌─────────────────────────────────────┐ │
└──────────────────────┘  │  │  Clustering (K-Means + PCA)         │ │
                          │  └─────────────────────────────────────┘ │
                          └──────────────────────────────────────────┘
```

---

## 📂 Estrutura de Diretórios

```
sinan-statistical-modeling/
│
├── sql/                        # Modelagem e scripts do banco de dados
│   ├── 01_schema.sql           # DDL — criação das tabelas e dimensões
│   ├── 02_functions_triggers.sql # CHECKs, validações e triggers de auditoria
│   ├── 03_views.sql            # Views pré-processadas
│   ├── 04_seed_dimensoes.sql   # Dados iniciais / seed
│   └── ERD.png                 # Diagrama Entidade-Relacionamento
│
├── scripts/                    # Pipeline ETL e banco
│   ├── etl.py                  # Script principal de ingestão e carga
│   ├── db_config.py            # Configuração do banco
│   ├── check_db.py             # Script de verificação
│   └── reset_db.py             # Script de reinicialização
│
├── notebook/                   # Análise exploratória e ML
│   ├── eda.ipynb               # Exploração e limpeza dos dados
│   └── analise_estatistica.ipynb # Modelagem de séries temporais e Clustering
│
├── interface/                  # Dashboard interativo
│   ├── dashboard.py            # Dashboard principal
│   └── dashboard_prophet.py    # Aplicação Streamlit completa (4 abas)
│
├── requirements.txt            # Dependências do projeto
├── .env.example                # Variáveis de ambiente (template)
├── LICENSE
└── README.md
```

> **Nota:** A estrutura acima é representativa. Nomes de arquivos podem variar conforme a implementação.

---

## Componentes Detalhados

### 1. Banco de Dados e Modelagem (`sql/`)

O banco de dados foi construído em **PostgreSQL** com uma abordagem **altamente normalizada**, garantindo integridade e rastreabilidade dos dados de saúde pública.

#### Tabelas de Domínio e Referência
| Tabela | Descrição |
|:-------|:----------|
| `tb_municipio` | Municípios brasileiros (código IBGE, nome, UF) |
| `tb_uf` | Unidades Federativas |
| `tb_unidade_saude` | Unidades de Saúde cadastradas no CNES |
| `tb_ocupacao` | Ocupações profissionais (CBO) |
| `tb_agravo` | Agravos/doenças notificáveis |
| `tb_pais` | Países de origem/residência |

#### Tabelas Centrais e Satélites
| Tabela | Descrição |
|:-------|:----------|
| `tb_notificacao` | Registro principal de cada notificação |
| `tb_paciente` | Dados demográficos do paciente |
| `tb_dados_clinicos` | Evolução clínica, sintomas, desfecho |
| `tb_geografia_epidemiologica` | Geolocalização epidemiológica |
| `tb_sistema_rastreabilidade` | Metadados de sistema (digitação, atualização) |
| `tb_auditoria` | Log em JSONB para rastreabilidade de alterações |

#### Segurança e Integridade
- **CHECK Constraints de Domínio** — Validações a nível de tabela para garantir valores válidos em campos clínicos.
- **Triggers de Validação Clínica** — Bloqueiam inserções ou atualizações inconsistentes (ex: paciente "curado" não pode possuir data de óbito, ou data de óbito anterior aos sintomas).
- **Triggers de Auditoria** — Toda alteração em registros críticos é logada em formato **JSONB** na `tb_auditoria`, preservando o histórico de mudanças genérico e seguro.
- **Materialized Views** — Agregações de KPIs pré-computadas (`mvw_kpi_cards`) para acelerar as consultas principais do dashboard.

---

### 2. ⚙ Pipeline ETL (`scripts/`)

O script `etl.py` é responsável por processar o CSV bruto do DataSUS e popular o banco PostgreSQL de forma alinhada com o modelo normalizado.

#### Principais Funcionalidades

- **🔑 Deduplicação Inteligente em Memória**
  Como a base não possui identificador de pessoa, o pipeline constrói uma **chave composta** de notificação:
  ```
  agravo + data_primeiros_sintomas + idade + sexo + município_residência + município_notificação
  ```
  O registro mantido é escolhido pela maior **completude**, data de digitação mais antiga e ausência de marcação de duplicidade (`NDUPLIC_N`). Os descartados são salvos em relatório de auditoria (`duplicatas_removidas.csv`).

- **Transformação e Limpeza Clínica**
  - Decodificação da variável complexa de idade (`NU_IDADE_N`) para anos inteiros (`idade_anos`).
  - Correção prévia de inconsistências clínicas impeditivas para não travar os lotes de banco (ex: ajusta *status* de óbito quando não há data).

- **Carga Otimizada**
  - Inserção de dimensões seguras utilizando `ON CONFLICT DO NOTHING`.
  - Processamento em **lotes alinhados posicionalmente** (ex: 20 mil) usando *bulk inserts* do `psycopg2.extras.execute_values` para as tabelas centrais e satélites.

---

### 3. 📊 Análise Exploratória e Machine Learning (`notebook/`)

#### EDA (Exploratory Data Analysis)
Limpeza exploratória e investigação das variáveis brutas: distribuições, valores faltantes, outliers e correlações entre variáveis epidemiológicas.

#### Modelagem Preditiva — Prophet
Utilização do **Prophet** (Meta/Facebook) para modelar a série temporal de notificações:
- Decomposição em **tendência**, **sazonalidade** e **feriados**.
- Projeção de semanas futuras com **intervalos de confiança**.
- Identificação de **changepoints** na curva de contaminação.

#### Clusterização Não-Supervisionada — K-Means + PCA
Agrupamento dos municípios brasileiros por **similaridade no perfil epidemiológico**:
- Redução de dimensionalidade com **PCA (Principal Component Analysis)**.
- Determinação do número ideal de clusters via **Silhouette Score** e **Elbow Method**.
- Identificação de padrões como:
  - Áreas com alta taxa de mortalidade
  - Regiões com indícios de subnotificação
  - Focos de epidemia aguda

---

### 4. 📈 Dashboard Interativo (`interface/`)

Interface gráfica construída em **Streamlit**, conectada em tempo real ao banco PostgreSQL, com **4 abas interativas**:

| Aba | Visualizações | Objetivo |
|:----|:-------------|:---------|
| **Sazonalidade** | Gráficos de linhas, boxplots interativos, decomposição aditiva | Identificar ciclos de surtos e padrões sazonais |
| **Tendência por UF** | Rankings dinâmicos, heatmaps (mapas de calor) | Comparar evolução entre Unidades Federativas |
| **Previsão (Prophet)** | Treino ao vivo, projeção com intervalos de confiança | Prever semanas futuras da curva de contaminação |
| **Clustering (K-Means)** | Scatter 2D com PCA, perfis de cluster | Agrupar municípios por semelhança epidemiológica |

---

## 🛠 Stack Tecnológica

<div align="center">

| Camada | Tecnologias |
|:-------|:-----------|
| **Linguagem** | Python 3.10+ |
| **Processamento** | Pandas, NumPy |
| **Banco de Dados** | PostgreSQL 15+, psycopg2, SQLAlchemy |
| **Visualização** | Streamlit, Plotly |
| **Machine Learning** | Scikit-Learn (K-Means, PCA, Silhouette), Prophet |
| **Estatística** | Statsmodels (Decomposição Sazonal) |

</div>

---

## 📝 Pré-requisitos

- **Python** ≥ 3.10
- **PostgreSQL** ≥ 15
- **pip** ou **conda** para gerenciamento de pacotes
- Arquivo CSV de notificações do SINAN/DataSUS (Zika Vírus)

---

## 🚀 Instalação e Configuração

### 1. Clone o repositório
```bash
git clone https://github.com/kiovaz/sinan-statistical-modeling.git
cd sinan-statistical-modeling
```

### 2. Crie e ative um ambiente virtual
```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
```

### 3. Instale as dependências
```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente
```bash
cp .env.example .env
# Edite o arquivo .env com as credenciais do seu PostgreSQL
```

### 5. Crie o banco de dados e execute os scripts SQL
```bash
psql -U seu_usuario -d seu_banco -f sql/01_schema.sql
psql -U seu_usuario -d seu_banco -f sql/02_functions_triggers.sql
psql -U seu_usuario -d seu_banco -f sql/03_views.sql
psql -U seu_usuario -d seu_banco -f sql/04_seed_dimensoes.sql
```

### 6. Execute o pipeline ETL
```bash
python scripts/etl.py
```

### 7. Inicie o dashboard
```bash
streamlit run interface/dashboard_prophet.py
```

---

## 💡 Uso

Após a instalação, acesse o dashboard em `http://localhost:8501` e navegue pelas abas:

1. **Sazonalidade** — Explore os ciclos temporais dos surtos de Zika.
2. **Tendência por UF** — Compare a evolução entre estados brasileiros.
3. **Previsão** — Treine o modelo Prophet ao vivo e projete cenários futuros.
4. **Clustering** — Visualize os agrupamentos de municípios e identifique padrões regionais.

---

## 📄 Licença

Este projeto está licenciado sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.

---

<div align="center">

*Dados públicos do SINAN/DataSUS — Ministério da Saúde*

</div>
