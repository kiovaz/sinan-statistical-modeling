-- 03_views.sql
-- Views analíticas para Dashboards (Modelo Normalizado)

-- 1. Série temporal semanal (Casos por Semana Epidemiológica)
CREATE OR REPLACE VIEW vw_serie_temporal_semanal AS
SELECT 
    n.nu_ano,
    c.sem_pri,
    COUNT(*) AS total_casos,
    SUM(CASE WHEN c.classi_fin = 1 THEN 1 ELSE 0 END) AS casos_confirmados
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
GROUP BY n.nu_ano, c.sem_pri
ORDER BY n.nu_ano, c.sem_pri;


-- 2. Casos por UF e Ano
CREATE OR REPLACE VIEW vw_casos_uf_ano AS
SELECT 
    u.sg_uf,
    n.nu_ano,
    COUNT(n.id_notificacao) AS total_notificacoes,
    SUM(CASE WHEN c.classi_fin = 1 THEN 1 ELSE 0 END) AS casos_confirmados
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
JOIN tb_geografia_epidemiologica g ON n.id_notificacao = g.id_notificacao
JOIN tb_municipio m ON g.id_municipio_resi = m.id_municipio
JOIN tb_uf u ON m.id_uf = u.id_uf
GROUP BY u.sg_uf, n.nu_ano
ORDER BY n.nu_ano, total_notificacoes DESC;


-- 3. Pirâmide Etária (Casos Confirmados)
CREATE OR REPLACE VIEW vw_piramide_etaria AS
SELECT 
    p.cs_sexo,
    CASE 
        WHEN p.idade_anos < 5 THEN '0-4 anos'
        WHEN p.idade_anos < 10 THEN '05-09 anos'
        WHEN p.idade_anos < 20 THEN '10-19 anos'
        WHEN p.idade_anos < 30 THEN '20-29 anos'
        WHEN p.idade_anos < 40 THEN '30-39 anos'
        WHEN p.idade_anos < 50 THEN '40-49 anos'
        WHEN p.idade_anos < 60 THEN '50-59 anos'
        WHEN p.idade_anos >= 60 THEN '60+ anos'
        ELSE 'Ignorado'
    END AS faixa_etaria,
    COUNT(*) AS total_casos_confirmados
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
JOIN tb_paciente p ON n.id_paciente = p.id_paciente
WHERE c.classi_fin = 1
GROUP BY 1, 2
ORDER BY faixa_etaria, p.cs_sexo;


-- 4. Vigilância de Gestantes
CREATE OR REPLACE VIEW vw_vigilancia_gestantes AS
SELECT 
    n.nu_ano,
    p.cs_gestant,
    COUNT(*) AS total_gestantes_notificadas,
    SUM(CASE WHEN c.classi_fin = 1 THEN 1 ELSE 0 END) AS gestantes_confirmadas_zika
FROM tb_notificacao n
JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
JOIN tb_paciente p ON n.id_paciente = p.id_paciente
WHERE p.cs_sexo = 'F' 
  AND p.cs_gestant IN (1, 2, 3, 4) -- 1 a 3 = Trimestres, 4 = Idade gestacional ignorada
GROUP BY n.nu_ano, p.cs_gestant
ORDER BY n.nu_ano DESC, p.cs_gestant;


-- 5. Cards de KPI (Key Performance Indicators)
CREATE OR REPLACE VIEW vw_kpi_cards AS
SELECT 
    (SELECT COUNT(*) FROM tb_notificacao) AS total_notificacoes_historico,
    (SELECT COUNT(*) FROM tb_dados_clinicos WHERE classi_fin = 1) AS total_casos_confirmados,
    (SELECT COUNT(*) FROM tb_dados_clinicos WHERE evolucao = 2) AS total_obitos_zika,
    (SELECT ROUND(COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM tb_dados_clinicos WHERE classi_fin = 1), 0), 2) 
     FROM tb_dados_clinicos 
     WHERE classi_fin = 1 AND evolucao = 2) AS taxa_letalidade_confirmados_pct;
