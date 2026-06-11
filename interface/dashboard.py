import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px
import plotly.graph_objects as go

# ==============================================================================
# 1. Configuração da Página do Streamlit
# ==============================================================================
try:
    st.set_page_config(
        page_title="Dashboard Epidemiológica - Zika Vírus",
        page_icon="🦟",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

# ==============================================================================
# 2. Conexão Segura com o Banco de Dados (NeonDB)
# ==============================================================================
@st.cache_resource
def init_connection():
    creds = st.secrets["postgres"]
    return psycopg2.connect(
        host=creds["host"],
        database=creds["database"],
        user=creds["user"],
        password=creds["password"],
        port=creds["port"],
        sslmode=creds["sslmode"]
    )

try:
    conn = init_connection()
except Exception as e:
    st.error(f"Erro ao conectar ao banco de dados: {e}")
    st.stop()

# ==============================================================================
# 3. Funções Auxiliares de Banco (Definidas antes do uso)
# ==============================================================================
def run_query(query, params=None):
    """Executa queries de forma segura retornando DataFrames vazios caso o banco falhe ou esteja vazio."""
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description is None:
                return pd.DataFrame()
            colnames = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            return pd.DataFrame(data, columns=colnames)
    except Exception:
        # Retorna DataFrame vazio silenciando exceções para manter o layout ativo sem travar
        return pd.DataFrame()

# ==============================================================================
# SIDEBAR - FILTROS GLOBAIS
# ==============================================================================
st.sidebar.title("Filtros de Vigilância")
st.sidebar.markdown("Consistente com a base **SINAN (2018–2026)**")

# Agora get_available_years enxerga perfeitamente a função run_query declarada acima
@st.cache_data(ttl=60)
def get_available_years():
    df = run_query("SELECT DISTINCT nu_ano FROM tb_notificacao ORDER BY nu_ano DESC;")
    if not df.empty and df['nu_ano'].notna().any():
        return df['nu_ano'].dropna().astype(int).tolist()
    return list(range(2026, 2017, -1)) # Fallback seguro de anos enquanto o banco está vazio

anos_disponiveis = get_available_years()
ano_selecionado = st.sidebar.selectbox("Selecione o Ano de Análise", anos_disponiveis)

st.sidebar.info(
    "💡 Os KPIs do topo representam o acumulado histórico total. "
    "Os gráficos abaixo respondem dinamicamente ao ano selecionado."
)

# Estado de espera amigável enquanto você não popula a semente (seed)
df_check = run_query("SELECT 1 FROM tb_notificacao LIMIT 1;")
if df_check.empty:
    st.sidebar.warning("⚠️ Modo de Espera: Nenhuns dados detectados no banco de dados. Exibindo templates de contingência.")

# ==============================================================================
# PAINEL PRINCIPAL
# ==============================================================================
st.title("🦟 Análise Estatística Epidemiológica — Zika Vírus")
st.markdown("### Monitoramento de Notificações Compulsórias (DataSUS/MS)")
st.write("---")

# ------------------------------------------------------------------------------
# SEÇÃO 1: CARDS DE KPI (Usa a Materialized View para máxima performance)
# ------------------------------------------------------------------------------
st.subheader("📊 Indicadores Chave de Desempenho Histórico (Acumulado)")

@st.cache_data(ttl=10)
def load_kpis():
    return run_query("SELECT * FROM mvw_kpi_cards;")

df_kpi = load_kpis()

col1, col2, col3, col4 = st.columns(4)

if not df_kpi.empty:
    kpi = df_kpi.iloc[0]
    
    val_notif = int(kpi['total_notificacoes_historico']) if pd.notna(kpi['total_notificacoes_historico']) else 0
    val_conf = int(kpi['total_casos_confirmados']) if pd.notna(kpi['total_casos_confirmados']) else 0
    val_obitos = int(kpi['total_obitos_zika']) if pd.notna(kpi['total_obitos_zika']) else 0
    taxa_letalidade = kpi['taxa_letalidade_confirmados_pct']
    taxa_valida = float(taxa_letalidade) if pd.notna(taxa_letalidade) else 0.0

    col1.metric(label="📋 Total de Notificações", value=f"{val_notif:,}".replace(",", "."))
    col2.metric(label="✅ Casos Confirmados", value=f"{val_conf:,}".replace(",", "."), delta="Zika Vírus +")
    col3.metric(label="💀 Óbitos por Zika", value=f"{val_obitos:,}".replace(",", "."))
    col4.metric(label="📉 Taxa de Letalidade", value=f"{taxa_valida:.2f}%", delta="S/ Confirmados", delta_color="inverse")
else:
    col1.metric(label="📋 Total de Notificações", value="0")
    col2.metric(label="✅ Casos Confirmados", value="0", delta="Aguardando carga")
    col3.metric(label="💀 Óbitos por Zika", value="0")
    col4.metric(label="📉 Taxa de Letalidade", value="0.00%", delta="Sem dados", delta_color="off")
    st.info("ℹ️ Os KPIs acima serão preenchidos automaticamente após a execução da Carga do ETL e o comando: 'REFRESH MATERIALIZED VIEW mvw_kpi_cards;'")

st.write("---")

# ------------------------------------------------------------------------------
# SEÇÃO 2: ANÁLISE TEMPORAL E GEOGRÁFICA DO ANO SELECIONADO
# ------------------------------------------------------------------------------
col_esq, col_dir = st.columns(2)

with col_esq:
    st.markdown(f"#### 📅 Série Temporal Semanal ({ano_selecionado})")
    
    query_temporal = """
        SELECT sem_pri, total_casos, casos_confirmados 
        FROM vw_serie_temporal_semanal 
        WHERE nu_ano = %s 
        ORDER BY sem_pri;
    """
    df_temporal = run_query(query_temporal, (ano_selecionado,))
    
    if not df_temporal.empty:
        df_temporal = df_temporal.dropna(subset=['sem_pri']).copy()
        df_temporal['sem_pri'] = df_temporal['sem_pri'].astype(float).astype(int).astype(str)
        
        # 2. Cria a máscara visual amigável (Muda de "202601" para "2026 - Sem 01")
        df_temporal['semana_formatada'] = df_temporal['sem_pri'].apply(
            lambda x: f"{x[:4]} - Sem {x[4:]}" if len(x) == 6 else x
        )
        # ==============================================================================

        fig_temp = px.line(
            df_temporal, 
            x="semana_formatada",  # <--- MUDADO AQUI: usa a nova coluna tratada como texto
            y=["total_casos", "casos_confirmados"],
            # Labels corrigidas para os eixos não ficarem com os nomes invertidos
            labels={"semana_formatada": "Semana Epidemiológica", "value": "Nº de Casos", "variable": "Indicador"},
            title=f"Casos por Semana Epidemiológica - Sintomas (sem_pri)",
            markers=True
        )
        
        # Garante que o Plotly trate o eixo X estritamente como categorias textuais sequenciais
        fig_temp.update_layout(
            xaxis=dict(type='category', tickangle=45),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
                st.plotly_chart(fig_uf, use_container_width=True)
    else:
        st.info(f"Sem dados geográficos registrados no banco para o ano {ano_selecionado}.")

st.write("---")

# ------------------------------------------------------------------------------
# SEÇÃO 3: DEMOGRAFIA (PIRÂMIDE ETÁRIA HISTÓRICA)
# ------------------------------------------------------------------------------
st.subheader("👥 Perfil Demográfico dos Casos Confirmados")

query_piramide = """
    SELECT cs_sexo, faixa_etaria, ordem_faixa, total_casos_confirmados 
    FROM vw_piramide_etaria
    ORDER BY ordem_faixa;
"""
df_piramide = run_query(query_piramide)

if not df_piramide.empty:
    categorias_faixa = df_piramide[['ordem_faixa', 'faixa_etaria']].drop_duplicates().sort_values('ordem_faixa')
    
    homens = categorias_faixa.merge(df_piramide[df_piramide['cs_sexo'] == 'M'], on=['ordem_faixa', 'faixa_etaria'], how='left').fillna(0)
    mulheres = categorias_faixa.merge(df_piramide[df_piramide['cs_sexo'] == 'F'], on=['ordem_faixa', 'faixa_etaria'], how='left').fillna(0)
    
    fig_piramide = go.Figure()
    
    fig_piramide.add_trace(go.Bar(
        y=homens['faixa_etaria'],
        x=homens['total_casos_confirmados'] * -1,
        name='Masculino',
        orientation='h',
        hovertemplate='Faixa: %{y}<br>Casos: %{customdata}<extra></extra>',
        customdata=homens['total_casos_confirmados'],
        marker=dict(color='#1f77b4')
    ))
    
    fig_piramide.add_trace(go.Bar(
        y=mulheres['faixa_etaria'],
        x=mulheres['total_casos_confirmados'],
        name='Feminino',
        orientation='h',
        hovertemplate='Faixa: %{y}<br>Casos: %{x}<extra></extra>',
        marker=dict(color='#e377c2')
    ))
    
    max_casos = int(df_piramide['total_casos_confirmados'].max())
    passo = max(1, max_casos // 3)
    
    tick_vals = list(range(-max_casos, max_casos + 1, passo))
    tick_text = [f"{abs(v):,}".replace(",", ".") for v in tick_vals]
    
    fig_piramide.update_layout(
        title="Pirâmide Etária — População Histórica Confirmada (Zika)",
        bargap=0.1,
        barmode='overlay',
        xaxis=dict(
            tickmode='array',
            tickvals=tick_vals,
            ticktext=tick_text,
            title="Quantidade de Casos"
        ),
        yaxis=dict(title="Faixas Etárias Ordenadas", type='category')
    )
    st.plotly_chart(fig_piramide, use_container_width=True)
else:
    st.info("Dados de pirâmide etária não disponíveis no banco atualmente.")

st.write("---")

# ------------------------------------------------------------------------------
# SEÇÃO 4: VIGILÂNCIA DE GESTANTES COM RISCO DE SÍNDROME CONGÊNITA
# ------------------------------------------------------------------------------
st.subheader("🤰 Vigilância Estratégica de Gestantes em Risco")
st.markdown(
    "> **Nota Epidemiológica:** O acompanhamento foca estritamente nos trimestres gestacionais "
    "1, 2 e 3 devido à correlação com a Síndrome Congênita do Zika Vírus (Microcefalia)."
)

query_gestantes = """
    SELECT trimestre, total_gestantes_notificadas, gestantes_confirmadas_zika 
    FROM vw_vigilancia_gestantes_risco
    WHERE nu_ano = %s
    ORDER BY trimestre;
"""
df_gest = run_query(query_gestantes, (ano_selecionado,))

if not df_gest.empty:
    mapa_trimestre = {1: "1º Trimestre", 2: "2º Trimestre", 3: "3º Trimestre"}
    df_gest['Trimestre_Label'] = df_gest['trimestre'].map(mapa_trimestre)
    
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        fig_gest_bar = px.bar(
            df_gest,
            x="Trimestre_Label",
            y=["total_gestantes_notificadas", "gestantes_confirmadas_zika"],
            barmode="group",
            labels={"value": "Total de Pacientes", "Trimestre_Label": "Período Gestacional", "variable": "Status"},
            title=f"Notificadas vs. Confirmadas por Trimestre Gestacional ({ano_selecionado})"
        )
        st.plotly_chart(fig_gest_bar, use_container_width=True)
        
    with col_g2:
        st.markdown(f"##### Tabela Consolidada de Monitoramento ({ano_selecionado})")
        df_gest_show = df_gest[['Trimestre_Label', 'total_gestantes_notificadas', 'gestantes_confirmadas_zika']].copy()
        df_gest_show.columns = ['Trimestre', 'Gestantes Notificadas', 'Casos Confirmados Zika']
        st.dataframe(df_gest_show, use_container_width=True, hide_index=True)
else:
    st.info(f"Nenhum registro crítico de gestantes elegíveis em {ano_selecionado} localizado no banco.")
