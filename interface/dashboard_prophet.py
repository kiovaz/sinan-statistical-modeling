"""
Dashboard — Zika Vírus SINAN 2018-2026
Baseado na análise estatística do notebook analise_estatistica.ipynb
"""

import os
import warnings
from datetime import datetime
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────
# Configuração da Página
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Zika Vírus — SINAN 2018-2026",
    page_icon="🦟",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Paleta epidemiológica (mesma do notebook)
COR_PRINCIPAL  = "#E63946"
COR_SECUNDARIA = "#457B9D"
COR_DESTAQUE   = "#F4A261"

# ─────────────────────────────────────────
# CSS customizado
# ─────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    [data-testid="collapsedControl"] { display: none; }
    [data-testid="stSidebar"]        { display: none; }
    .metric-card {
        background: #f8f9fa;
        border-left: 4px solid #E63946;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    .section-title { color: #1d3557; font-weight: 700; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────
def semana_para_data(row):
    try:
        return datetime.fromisocalendar(int(row["nu_ano"]), int(row["sem_pri"]), 1)
    except (ValueError, TypeError):
        return pd.NaT


def build_database_url():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        user     = os.getenv("PGUSER", "")
        password = os.getenv("PGPASSWORD", "")
        host     = os.getenv("PGHOST", "")
        database = os.getenv("PGDATABASE", "")
        sslmode  = os.getenv("PGSSLMODE", "require")
        if all([user, password, host, database]):
            url = (
                f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
                f"@{host}/{database}?sslmode={sslmode}"
            )
    return url


@st.cache_resource(show_spinner=False)
def get_engine(database_url: str):
    from sqlalchemy import create_engine
    return create_engine(database_url, pool_pre_ping=True)


@st.cache_data(ttl=3600, show_spinner=False)
def query_df(_engine, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, _engine)

# Conexão automática via variáveis de ambiente / .env
database_url = build_database_url()

if not database_url:
    st.error("Credenciais do banco não encontradas.")
    st.stop()
# ─────────────────────────────────────────
# Conecta ao banco
# ─────────────────────────────────────────
try:
    engine = get_engine(database_url)
except Exception as e:
    st.error(f"Falha ao criar engine: {e}")
    st.stop()


# ─────────────────────────────────────────
# Header principal
# ─────────────────────────────────────────
st.title("Zika Vírus SINAN 2018-2026")
st.caption("Análise epidemiológica | Fonte: SINAN — DataSUS/MS")

tab1, tab2, tab3, tab4 = st.tabs([
    "Sazonalidade",
    "Tendência por UF",
    "Previsão (Prophet)",
    "Clustering (K-Means)",
])


# ═══════════════════════════════════════════════════════════
# TAB 1 — SAZONALIDADE
# ═══════════════════════════════════════════════════════════
with tab1:
    st.header("Análise de Sazonalidade")
    st.caption("Padrões cíclicos na incidência semanal de Zika (2018-2026).")

    with st.spinner("Carregando série temporal..."):
        try:
            df_semanal = query_df(engine, """
                SELECT * FROM vw_serie_temporal_semanal
                WHERE nu_ano BETWEEN 2018 AND 2026
                ORDER BY nu_ano, sem_pri;
            """)
        except Exception as e:
            st.error(f"Erro ao consultar vw_serie_temporal_semanal: {e}")
            st.stop()

    df_semanal["ds"] = pd.to_datetime(df_semanal.apply(semana_para_data, axis=1))
    df_semanal = (
        df_semanal.dropna(subset=["ds"])
        .sort_values("ds")
        .reset_index(drop=True)
    )

    # ── Métricas rápidas ──
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Total de Semanas", f"{len(df_semanal)}")
    col_m2.metric("Total de Notificações", f"{df_semanal['total_casos'].sum():,.0f}")
    col_m3.metric("Casos Confirmados", f"{df_semanal['casos_confirmados'].sum():,.0f}")
    col_m4.metric(
        "Taxa de Confirmação",
        f"{df_semanal['casos_confirmados'].sum() / df_semanal['total_casos'].sum() * 100:.1f}%",
    )

    st.divider()

    # ── 1.1 Série temporal completa ──
    st.subheader("Série Temporal Semanal — Notificações × Confirmados")
    fig_serie = go.Figure()
    fig_serie.add_trace(go.Scatter(
        x=df_semanal["ds"], y=df_semanal["total_casos"],
        name="Total de Notificações",
        line=dict(color=COR_SECUNDARIA, width=1.2),
        opacity=0.65,
    ))
    fig_serie.add_trace(go.Scatter(
        x=df_semanal["ds"], y=df_semanal["casos_confirmados"],
        name="Casos Confirmados",
        line=dict(color=COR_PRINCIPAL, width=1.8),
    ))
    fig_serie.update_layout(
        xaxis_title="Data (semana epidemiológica)",
        yaxis_title="Nº de Casos",
        legend=dict(orientation="h", y=1.08),
        height=380,
        margin=dict(t=20, b=40),
        hovermode="x unified",
    )
    st.plotly_chart(fig_serie, use_container_width=True)

    # ── 1.2 Boxplot mensal + Heatmap ──
    df_semanal["mes"]      = df_semanal["ds"].dt.month
    df_semanal["nome_mes"] = df_semanal["ds"].dt.strftime("%b")
    ORDEM_MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    col_box, col_heat = st.columns(2)

    with col_box:
        st.subheader("Sazonalidade Mensal")
        fig_box = px.box(
            df_semanal,
            x="nome_mes", y="total_casos",
            category_orders={"nome_mes": ORDEM_MESES},
            color="nome_mes",
            color_discrete_sequence=px.colors.sequential.YlOrRd,
            labels={"total_casos": "Casos / semana", "nome_mes": "Mês"},
        )
        fig_box.update_layout(showlegend=False, height=380, margin=dict(t=20))
        st.plotly_chart(fig_box, use_container_width=True)

    with col_heat:
        st.subheader("Heatmap — Semana Epidemiológica × Ano")
        pivot_sem = df_semanal.pivot_table(
            index="sem_pri", columns="nu_ano",
            values="total_casos", fill_value=0,
        )
        fig_heat = px.imshow(
            pivot_sem,
            color_continuous_scale="YlOrRd",
            labels=dict(x="Ano", y="Semana Epidemiológica", color="Casos"),
            aspect="auto",
        )
        fig_heat.update_layout(height=380, margin=dict(t=20))
        st.plotly_chart(fig_heat, use_container_width=True)

    # ── 1.3 Decomposição sazonal ──
    with st.expander("Decomposição Sazonal (Tendência + Sazonalidade + Resíduo)", expanded=False):
        st.info("Decomposição aditiva com período de 52 semanas.")
        try:
            from statsmodels.tsa.seasonal import seasonal_decompose

            ts = (
                df_semanal.set_index("ds")["total_casos"]
                .resample("W-MON")
                .sum()
                .fillna(0)
            )
            resultado = seasonal_decompose(ts, model="additive", period=52)

            componentes = {
                "Série Original": ts,
                "Tendência": resultado.trend,
                "Sazonalidade": resultado.seasonal,
                "Resíduo": resultado.resid,
            }
            for nome, serie in componentes.items():
                cor = COR_PRINCIPAL if nome == "Tendência" else COR_SECUNDARIA
                fig_c = px.line(
                    x=serie.index, y=serie.values,
                    labels={"x": "Data", "y": nome},
                    title=nome,
                )
                fig_c.update_traces(line_color=cor)
                fig_c.update_layout(height=200, margin=dict(t=30, b=20))
                st.plotly_chart(fig_c, use_container_width=True)
        except ImportError:
            st.warning("Instale statsmodels: `pip install statsmodels`")
        except Exception as e:
            st.error(f"Erro na decomposição: {e}")


# ═══════════════════════════════════════════════════════════
# TAB 2 — TENDÊNCIA POR UF
# ═══════════════════════════════════════════════════════════
with tab2:
    st.header("Tendência por UF")
    st.caption("Evolução temporal dos casos confirmados por Unidade Federativa.")

    with st.spinner("Carregando dados por UF..."):
        try:
            df_uf = query_df(engine, "SELECT * FROM vw_casos_uf_ano;")
        except Exception as e:
            st.error(f"Erro ao consultar vw_casos_uf_ano: {e}")
            st.stop()

    # ── Heatmap UF × Ano ──
    st.subheader("Heatmap — Casos Confirmados por UF e Ano")
    pivot_uf = df_uf.pivot_table(
        index="sg_uf", columns="nu_ano",
        values="casos_confirmados", fill_value=0,
    )
    ordem_uf = pivot_uf.sum(axis=1).sort_values(ascending=False).index
    pivot_uf = pivot_uf.loc[ordem_uf]

    fig_huf = px.imshow(
        pivot_uf,
        text_auto="g",
        color_continuous_scale="YlOrRd",
        labels=dict(x="Ano", y="UF (ord. por total)", color="Confirmados"),
        aspect="auto",
    )
    fig_huf.update_layout(height=560, margin=dict(t=20))
    st.plotly_chart(fig_huf, use_container_width=True)

    col_top5, col_rank = st.columns([3, 2])

    # ── Top 5 UFs ──
    with col_top5:
        st.subheader("Evolução Temporal — Top 5 UFs")
        top5_ufs = (
            df_uf.groupby("sg_uf")["casos_confirmados"]
            .sum().nlargest(5).index.tolist()
        )
        df_top5 = df_uf[df_uf["sg_uf"].isin(top5_ufs)].sort_values("nu_ano")
        fig_top5 = px.line(
            df_top5,
            x="nu_ano", y="casos_confirmados", color="sg_uf",
            markers=True,
            labels={"nu_ano": "Ano", "casos_confirmados": "Casos Confirmados", "sg_uf": "UF"},
            color_discrete_sequence=px.colors.qualitative.Set1,
        )
        fig_top5.update_layout(
            height=380,
            legend=dict(orientation="h", y=1.05),
            xaxis=dict(tickmode="linear"),
            margin=dict(t=20),
        )
        st.plotly_chart(fig_top5, use_container_width=True)

    # ── Ranking acumulado ──
    with col_rank:
        st.subheader("Ranking Acumulado")
        ranking = (
            df_uf.groupby("sg_uf")[["total_notificacoes", "casos_confirmados"]]
            .sum()
            .sort_values("casos_confirmados", ascending=True)
            .reset_index()
        )
        fig_rank = go.Figure()
        fig_rank.add_trace(go.Bar(
            y=ranking["sg_uf"], x=ranking["total_notificacoes"],
            name="Notificações", orientation="h", marker_color=COR_SECUNDARIA,
        ))
        fig_rank.add_trace(go.Bar(
            y=ranking["sg_uf"], x=ranking["casos_confirmados"],
            name="Confirmados", orientation="h", marker_color=COR_PRINCIPAL,
        ))
        fig_rank.update_layout(
            barmode="group",
            height=380,
            xaxis_title="Nº de Casos",
            yaxis_title="UF",
            legend=dict(orientation="h", y=1.05),
            margin=dict(t=20, l=40),
        )
        st.plotly_chart(fig_rank, use_container_width=True)

    # ── Tabela interativa ──
    with st.expander("Tabela completa por UF e Ano"):
        uf_sel = st.multiselect("Filtrar por UF:", sorted(df_uf["sg_uf"].unique()), default=[])
        df_show = df_uf if not uf_sel else df_uf[df_uf["sg_uf"].isin(uf_sel)]
        st.dataframe(
            df_show.sort_values(["nu_ano", "sg_uf"]),
            use_container_width=True,
            height=300,
        )


# ═══════════════════════════════════════════════════════════
# TAB 3 — PROPHET
# ═══════════════════════════════════════════════════════════
with tab3:
    st.header("Previsão de Casos — Prophet")
    st.caption(
        "Modelo aditivo de séries temporais (Meta / Prophet) com "
        "sazonalidade anual e tendência flexível."
    )

    col_cfg, _ = st.columns([2, 3])
    with col_cfg:
        periodos = st.slider("Semanas de previsão:", 4, 104, 52, step=4)
        cp_scale = st.slider("Flexibilidade da tendência (changepoint_prior_scale):", 0.01, 0.5, 0.05)

    if st.button("Treinar Prophet e gerar previsão", type="primary"):
        try:
            from prophet import Prophet

            with st.spinner("Carregando série e treinando modelo..."):
                df_sp = query_df(engine, """
                    SELECT * FROM vw_serie_temporal_semanal
                    WHERE nu_ano BETWEEN 2018 AND 2026
                    ORDER BY nu_ano, sem_pri;
                """)
                df_sp["ds"] = pd.to_datetime(df_sp.apply(semana_para_data, axis=1))
                df_sp = df_sp.dropna(subset=["ds"]).sort_values("ds").reset_index(drop=True)

                df_prophet = (
                    df_sp[["ds", "total_casos"]]
                    .rename(columns={"total_casos": "y"})
                    .query("'2018-01-01' <= ds <= '2026-12-31'")
                    .sort_values("ds")
                    .reset_index(drop=True)
                )

                modelo = Prophet(
                    seasonality_mode="additive",
                    yearly_seasonality=True,
                    weekly_seasonality=False,
                    daily_seasonality=False,
                    changepoint_prior_scale=cp_scale,
                    interval_width=0.95,
                )
                modelo.fit(df_prophet)

                futuro   = modelo.make_future_dataframe(periods=periodos, freq="W")
                previsao = modelo.predict(futuro)

            st.success(f"Modelo treinado | Previsão até {previsao['ds'].max().date()}")

            # ── Gráfico principal ──
            st.subheader("Histórico + Previsão")
            fig_prev = go.Figure()

            # IC 95%
            x_band = previsao["ds"].tolist() + previsao["ds"].tolist()[::-1]
            y_band = previsao["yhat_upper"].tolist() + previsao["yhat_lower"].tolist()[::-1]
            fig_prev.add_trace(go.Scatter(
                x=x_band, y=y_band,
                fill="toself",
                fillcolor="rgba(69, 123, 157, 0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                name="IC 95%",
            ))

            # Linha de separação histórico/futuro
            ult_historico = df_prophet["ds"].max()
            fig_prev.add_vline(
                x=ult_historico, line_dash="dot",
                line_color="gray", opacity=0.6,
                annotation_text="Hoje",
            )

            # Dados históricos
            fig_prev.add_trace(go.Scatter(
                x=df_prophet["ds"], y=df_prophet["y"],
                mode="markers",
                marker=dict(color="black", size=2.5, opacity=0.4),
                name="Histórico",
            ))

            # Previsão
            fig_prev.add_trace(go.Scatter(
                x=previsao["ds"], y=previsao["yhat"],
                line=dict(color=COR_PRINCIPAL, width=2.2),
                name="Previsão (yhat)",
            ))

            fig_prev.update_layout(
                xaxis_title="Data",
                yaxis_title="Nº de Casos",
                height=420,
                legend=dict(orientation="h", y=1.08),
                hovermode="x unified",
                margin=dict(t=20),
            )
            st.plotly_chart(fig_prev, use_container_width=True)

            # ── Componentes ──
            st.subheader("Componentes do Modelo")
            col_t, col_s = st.columns(2)

            with col_t:
                fig_trend = px.line(
                    previsao, x="ds", y="trend",
                    title="Tendência",
                    labels={"ds": "Data", "trend": "Tendência"},
                )
                fig_trend.update_traces(line_color=COR_PRINCIPAL)
                fig_trend.update_layout(height=280, margin=dict(t=35, b=20))
                st.plotly_chart(fig_trend, use_container_width=True)

            with col_s:
                fig_seas = px.line(
                    previsao.sort_values("ds"),
                    x="ds", y="yearly",
                    title="Sazonalidade Anual",
                    labels={"ds": "Data", "yearly": "Efeito Sazonal"},
                )
                fig_seas.update_traces(line_color=COR_SECUNDARIA)
                fig_seas.update_layout(height=280, margin=dict(t=35, b=20))
                st.plotly_chart(fig_seas, use_container_width=True)

            # ── Tabela de previsão futura ──
            with st.expander("Valores previstos — próximas semanas"):
                fut_only = previsao[previsao["ds"] > ult_historico][
                    ["ds", "yhat", "yhat_lower", "yhat_upper"]
                ].copy()
                fut_only.columns = ["Data", "Previsão", "IC Inferior (95%)", "IC Superior (95%)"]
                fut_only = fut_only.round(0).astype({"Previsão": int, "IC Inferior (95%)": int, "IC Superior (95%)": int})
                st.dataframe(fut_only, use_container_width=True, height=300)

        except ImportError:
            st.error("Prophet não está instalado. Execute: `pip install prophet`")
        except Exception as e:
            st.error(f"Erro ao treinar o modelo: {e}")
            st.exception(e)
    else:
        st.info("Clique no botão acima para iniciar o treinamento do Prophet.")


# ═══════════════════════════════════════════════════════════
# TAB 4 — K-MEANS
# ═══════════════════════════════════════════════════════════
with tab4:
    st.header("Agrupamento de Municípios — K-Means")
    st.caption(
        "Clusterização por perfil epidemiológico: "
        "alta incidência, subnotificação ou baixo risco."
    )

    SQL_FEATURES = """
    SELECT
        g.id_municipio_resi,
        m.nm_municipio,
        u.sg_uf,
        COUNT(*)                                                              AS total_notificacoes,
        COUNT(*) FILTER (WHERE c.classi_fin = 1)                              AS confirmados,
        COUNT(*) FILTER (WHERE c.evolucao = 2)                                AS obitos,
        ROUND(COUNT(*) FILTER (WHERE c.classi_fin = 1) * 100.0
              / NULLIF(COUNT(*), 0), 2)                                        AS taxa_confirmacao_pct,
        ROUND(COUNT(*) FILTER (WHERE c.evolucao = 2 AND c.classi_fin = 1) * 100.0
              / NULLIF(COUNT(*) FILTER (WHERE c.classi_fin = 1), 0), 2)        AS taxa_letalidade_pct,
        ROUND(AVG(p.idade_anos)::numeric, 1)                                   AS media_idade,
        ROUND(COUNT(*) FILTER (WHERE p.cs_sexo = 'F') * 100.0
              / NULLIF(COUNT(*), 0), 2)                                        AS pct_feminino,
        ROUND(COUNT(*) FILTER (WHERE p.cs_gestant IN (1,2,3)) * 100.0
              / NULLIF(COUNT(*), 0), 2)                                        AS pct_gestantes
    FROM tb_notificacao n
    JOIN tb_dados_clinicos c           ON n.id_notificacao = c.id_notificacao
    JOIN tb_paciente p                 ON n.id_paciente = p.id_paciente
    JOIN tb_geografia_epidemiologica g ON n.id_notificacao = g.id_notificacao
    JOIN tb_municipio m                ON g.id_municipio_resi = m.id_municipio
    JOIN tb_uf u                       ON m.id_uf = u.id_uf
    GROUP BY g.id_municipio_resi, m.nm_municipio, u.sg_uf
    HAVING COUNT(*) >= 10
    ORDER BY total_notificacoes DESC;
    """

    with st.spinner("Carregando features dos municípios..."):
        try:
            df_mun = query_df(engine, SQL_FEATURES)
        except Exception as e:
            st.error(f"Erro ao carregar municípios: {e}")
            st.stop()

    st.success(f"{len(df_mun)} municípios com ≥ 10 notificações carregados")

    FEATURES = [
        "total_notificacoes", "confirmados", "obitos",
        "taxa_confirmacao_pct", "taxa_letalidade_pct",
        "media_idade", "pct_feminino", "pct_gestantes",
    ]

    try:
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        st.error("scikit-learn não está instalado. Execute: `pip install scikit-learn`")
        st.stop()

    X = df_mun[FEATURES].fillna(0)
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # ── Elbow + Silhouette ──
    st.subheader("Seleção de K — Cotovelo + Silhouette")
    K_range  = range(2, 9)
    inertias  = []
    sil_scores = []

    with st.spinner("Calculando K ideal (pode levar alguns segundos)..."):
        for k in K_range:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            km.fit(X_scaled)
            inertias.append(km.inertia_)
            sil_scores.append(silhouette_score(X_scaled, km.labels_))

    melhor_k = list(K_range)[int(np.argmax(sil_scores))]

    col_elb, col_sil = st.columns(2)

    with col_elb:
        fig_elb = px.line(
            x=list(K_range), y=inertias,
            markers=True,
            title="Método do Cotovelo",
            labels={"x": "K (nº de clusters)", "y": "Inércia"},
        )
        fig_elb.update_traces(line_color=COR_SECUNDARIA, marker_color=COR_SECUNDARIA)
        fig_elb.update_layout(height=300, margin=dict(t=35, b=20))
        st.plotly_chart(fig_elb, use_container_width=True)

    with col_sil:
        cores_sil = [COR_DESTAQUE if k == melhor_k - 2 else COR_SECUNDARIA for k in range(len(list(K_range)))]
        fig_sil = px.bar(
            x=list(K_range), y=sil_scores,
            title="Silhouette Score por K",
            labels={"x": "K", "y": "Silhouette Score"},
        )
        fig_sil.update_traces(marker_color=[COR_DESTAQUE if k == melhor_k else COR_SECUNDARIA for k in K_range])
        fig_sil.update_layout(height=300, margin=dict(t=35, b=20))
        st.plotly_chart(fig_sil, use_container_width=True)

    st.info(f"K sugerido pelo Silhouette: **{melhor_k}** (score = {max(sil_scores):.4f})")

    # ── Clustering final ──
    st.subheader("Clustering Final")
    k_escolhido = st.slider("Escolha o K:", 2, 8, melhor_k, key="k_slider")

    km_final = KMeans(n_clusters=k_escolhido, random_state=42, n_init=10)
    df_mun   = df_mun.copy()
    df_mun["cluster"] = km_final.fit_predict(X_scaled).astype(str)

    dist = df_mun["cluster"].value_counts().sort_index()
    cols_dist = st.columns(len(dist))
    for i, (cl, cnt) in enumerate(dist.items()):
        cols_dist[i].metric(f"Cluster {cl}", f"{cnt} municípios")

    # ── PCA 2D ──
    st.subheader("Visualização 2D — PCA")
    pca   = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_scaled)
    ve    = pca.explained_variance_ratio_

    df_pca = pd.DataFrame({
        "PC1": X_pca[:, 0],
        "PC2": X_pca[:, 1],
        "cluster":       df_mun["cluster"],
        "Município":     df_mun["nm_municipio"],
        "UF":            df_mun["sg_uf"],
        "Notificações":  df_mun["total_notificacoes"],
        "Confirmados":   df_mun["confirmados"],
        "Tx. Confirm. (%)": df_mun["taxa_confirmacao_pct"],
    })

    fig_pca = px.scatter(
        df_pca,
        x="PC1", y="PC2",
        color="cluster",
        hover_data=["Município", "UF", "Notificações", "Confirmados", "Tx. Confirm. (%)"],
        title=f"Clusters de Municípios — PCA 2D (K={k_escolhido})",
        labels={
            "PC1": f"PC1 ({ve[0]*100:.1f}% var.)",
            "PC2": f"PC2 ({ve[1]*100:.1f}% var.)",
        },
        opacity=0.75,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_pca.update_layout(height=480, margin=dict(t=40))
    st.plotly_chart(fig_pca, use_container_width=True)

    # ── Perfil dos clusters ──
    st.subheader("Perfil Médio dos Clusters")
    perfil = df_mun.groupby("cluster")[FEATURES].mean().round(2)

    fig_perfil = px.imshow(
        perfil[FEATURES].T,
        text_auto=".1f",
        color_continuous_scale="YlGnBu",
        labels=dict(x="Cluster", y="Feature", color="Média"),
        title="Heatmap de Perfil por Cluster",
        aspect="auto",
    )
    fig_perfil.update_layout(height=380, margin=dict(t=40))
    st.plotly_chart(fig_perfil, use_container_width=True)

    with st.expander("Tabela de perfil + ranking de municípios por cluster"):
        st.markdown("**Perfil médio:**")
        st.dataframe(perfil, use_container_width=True)

        st.markdown("---")
        cl_sel = st.selectbox("Ver top municípios do cluster:", sorted(df_mun["cluster"].unique()))
        top_mun = (
            df_mun[df_mun["cluster"] == cl_sel]
            .nlargest(15, "total_notificacoes")
            [[
                "nm_municipio", "sg_uf", "total_notificacoes",
                "confirmados", "taxa_confirmacao_pct", "taxa_letalidade_pct",
            ]]
            .rename(columns={
                "nm_municipio": "Município", "sg_uf": "UF",
                "total_notificacoes": "Notificações", "confirmados": "Confirmados",
                "taxa_confirmacao_pct": "Tx. Confirm. (%)", "taxa_letalidade_pct": "Tx. Letal. (%)",
            })
        )
        st.dataframe(top_mun, use_container_width=True)
