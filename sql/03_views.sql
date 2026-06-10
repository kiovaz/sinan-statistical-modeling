-- 03_views.sql
-- Views analíticas para Dashboards (Modelo Normalizado)
-- ===========================================================================
-- CORREÇÕES NESTA VERSÃO:
--   [ALTA]  vw_piramide_etaria: ordenação numérica (era alfabética -> 60+ vinha antes de 0-4)
--   [BAIXA] vw_kpi_cards convertida em MATERIALIZED VIEW (evita 4 full scans no dashboard)
--   [EXTRA] vw_vigilancia_gestantes_risco: só trimestres 1,2,3 (risco de sínd. congênita)
-- ===========================================================================

-- 1. Série temporal semanal (Casos por Semana Epidemiológica)
--    Usa sem_pri (semana dos primeiros sintomas) conforme recomendação do catálogo.
CREATE OR REPLACE VIEW vw_serie_temporal_semanal AS
SELECT
    n.nu_ano,
    c.sem_pri,
    COUNT(*) AS total_casos,
    COUNT(*) FILTER (WHERE c.classi_fin = 1) AS casos_confirmados
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
GROUP BY n.nu_ano, c.sem_pri
ORDER BY n.nu_ano, c.sem_pri;


-- 2. Casos por UF e Ano (por UF de residência)
CREATE OR REPLACE VIEW vw_casos_uf_ano AS
SELECT
    u.sg_uf,
    n.nu_ano,
    COUNT(n.id_notificacao) AS total_notificacoes,
    COUNT(*) FILTER (WHERE c.classi_fin = 1) AS casos_confirmados
FROM tb_notificacao n
JOIN tb_dados_clinicos c            ON n.id_notificacao = c.id_notificacao
JOIN tb_geografia_epidemiologica g  ON n.id_notificacao = g.id_notificacao
JOIN tb_municipio m                 ON g.id_municipio_resi = m.id_municipio
JOIN tb_uf u                        ON m.id_uf = u.id_uf
GROUP BY u.sg_uf, n.nu_ano
ORDER BY n.nu_ano, total_notificacoes DESC;


-- 3. Pirâmide Etária (Casos Confirmados)
--    Coluna ordem_faixa garante ordenação cronológica correta no dashboard.
CREATE OR REPLACE VIEW vw_piramide_etaria AS
SELECT
    p.cs_sexo,
    CASE
        WHEN p.idade_anos < 5  THEN '0-4 anos'
        WHEN p.idade_anos < 10 THEN '05-09 anos'
        WHEN p.idade_anos < 20 THEN '10-19 anos'
        WHEN p.idade_anos < 30 THEN '20-29 anos'
        WHEN p.idade_anos < 40 THEN '30-39 anos'
        WHEN p.idade_anos < 50 THEN '40-49 anos'
        WHEN p.idade_anos < 60 THEN '50-59 anos'
        WHEN p.idade_anos >= 60 THEN '60+ anos'
        ELSE 'Ignorado'
    END AS faixa_etaria,
    CASE
        WHEN p.idade_anos < 5  THEN 1
        WHEN p.idade_anos < 10 THEN 2
        WHEN p.idade_anos < 20 THEN 3
        WHEN p.idade_anos < 30 THEN 4
        WHEN p.idade_anos < 40 THEN 5
        WHEN p.idade_anos < 50 THEN 6
        WHEN p.idade_anos < 60 THEN 7
        WHEN p.idade_anos >= 60 THEN 8
        ELSE 9
    END AS ordem_faixa,
    COUNT(*) AS total_casos_confirmados
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
JOIN tb_paciente p       ON n.id_paciente = p.id_paciente
WHERE c.classi_fin = 1
GROUP BY faixa_etaria, ordem_faixa, p.cs_sexo
ORDER BY ordem_faixa, p.cs_sexo;


-- 4. Vigilância de Gestantes (todas as gestantes notificadas: trimestres 1-3 + ignorada=4)
CREATE OR REPLACE VIEW vw_vigilancia_gestantes AS
SELECT
    n.nu_ano,
    p.cs_gestant,
    COUNT(*) AS total_gestantes_notificadas,
    COUNT(*) FILTER (WHERE c.classi_fin = 1) AS gestantes_confirmadas_zika
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
JOIN tb_paciente p       ON n.id_paciente = p.id_paciente
WHERE p.cs_sexo = 'F'
  AND p.cs_gestant IN (1, 2, 3, 4)  -- 1-3 = trimestres, 4 = idade gestacional ignorada
GROUP BY n.nu_ano, p.cs_gestant
ORDER BY n.nu_ano DESC, p.cs_gestant;


-- 4b. Vigilância de Gestantes COM RISCO de síndrome congênita (só trimestres 1, 2, 3)
--     Recorte mais estrito alinhado ao enunciado (risco de síndrome congênita).
CREATE OR REPLACE VIEW vw_vigilancia_gestantes_risco AS
SELECT
    n.nu_ano,
    p.cs_gestant AS trimestre,
    COUNT(*) AS total_gestantes_notificadas,
    COUNT(*) FILTER (WHERE c.classi_fin = 1) AS gestantes_confirmadas_zika
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
JOIN tb_paciente p       ON n.id_paciente = p.id_paciente
WHERE p.cs_sexo = 'F'
  AND p.cs_gestant IN (1, 2, 3)
GROUP BY n.nu_ano, p.cs_gestant
ORDER BY n.nu_ano DESC, p.cs_gestant;


-- 5. Cards de KPI — MATERIALIZED VIEW
--    Materializada porque são 4 agregações pesadas sobre 236k linhas; recalcular
--    a cada abertura do dashboard travaria. Atualize com:
--        REFRESH MATERIALIZED VIEW mvw_kpi_cards;
--    (agende via cron/pg_cron após cada carga de ETL).
DROP MATERIALIZED VIEW IF EXISTS mvw_kpi_cards;
CREATE MATERIALIZED VIEW mvw_kpi_cards AS
SELECT
    (SELECT COUNT(*) FROM tb_notificacao)                              AS total_notificacoes_historico,
    (SELECT COUNT(*) FROM tb_dados_clinicos WHERE classi_fin = 1)      AS total_casos_confirmados,
    (SELECT COUNT(*) FROM tb_dados_clinicos WHERE evolucao = 2)        AS total_obitos_zika,
    (SELECT ROUND(
        COUNT(*) FILTER (WHERE evolucao = 2 AND classi_fin = 1) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE classi_fin = 1), 0), 2)
     FROM tb_dados_clinicos)                                           AS taxa_letalidade_confirmados_pct;
