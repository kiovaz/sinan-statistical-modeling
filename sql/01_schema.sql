-- 01_schema.sql
-- Modelagem Relacional Altamente Normalizada para Zika Vírus (SINAN)
-- ===========================================================================
-- CORREÇÕES APLICADAS NESTA VERSÃO:
--   [ALTA]  CHECK constraints em tb_dados_clinicos (classi_fin, criterio, evolucao)
--   [OBS]   cs_flxret / flxrecebi continuam INTEGER (ETL converte char->int)
--   [OBS]   nu_idade_n ampliado p/ VARCHAR(10) (evita truncamento silencioso)
-- NOTA SOBRE DEDUPLICAÇÃO:
--   A base NÃO possui NU_CNS nem qualquer identificador de pessoa (confirmado
--   nas colunas do CSV). Logo NÃO há deduplicação de pacientes — apenas de
--   NOTIFICAÇÕES, feita no ETL (staging) por chave composta:
--     ID_AGRAVO + DT_SIN_PRI + NU_IDADE_N + CS_SEXO + ID_MN_RESI + ID_MUNICIP
--   (reforçada por NDUPLIC_N quando preenchido).
-- ===========================================================================

-- =======================================================
-- 1. Tabelas de Domínio e Referência Geográfica/Saúde
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_uf (
    id_uf INTEGER PRIMARY KEY,
    sg_uf VARCHAR(2) NOT NULL,
    nm_uf VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS tb_municipio (
    id_municipio INTEGER PRIMARY KEY,
    id_uf INTEGER REFERENCES tb_uf(id_uf),
    nm_municipio VARCHAR(150),
    id_regional INTEGER
);

CREATE TABLE IF NOT EXISTS tb_unidade_saude (
    id_cnes VARCHAR(20) PRIMARY KEY,
    id_municipio INTEGER REFERENCES tb_municipio(id_municipio),
    nm_unidade VARCHAR(200),
    tp_unidade VARCHAR(2)
);

CREATE TABLE IF NOT EXISTS tb_ocupacao (
    id_cbo VARCHAR(10) PRIMARY KEY,
    nm_ocupacao VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS tb_agravo (
    id_cid VARCHAR(10) PRIMARY KEY,
    nm_agravo VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS tb_pais (
    id_pais INTEGER PRIMARY KEY,
    nm_pais VARCHAR(100)
);

-- =======================================================
-- 2. Tabela de Pacientes (Demografia)
--    nu_idade_n ampliado p/ VARCHAR(10) (alguns registros estouram 4 chars)
--    SEM nu_cns: a base não traz identificador de pessoa.
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_paciente (
    id_paciente BIGSERIAL PRIMARY KEY,
    id_cbo VARCHAR(10) REFERENCES tb_ocupacao(id_cbo),
    cs_sexo CHAR(1),
    nu_idade_n VARCHAR(10),
    idade_anos INTEGER,
    cs_gestant INTEGER,
    cs_raca INTEGER,
    cs_escolaridade INTEGER
);

-- =======================================================
-- 3. Tabela Central de Notificações
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_notificacao (
    id_notificacao BIGSERIAL PRIMARY KEY,
    id_paciente BIGINT REFERENCES tb_paciente(id_paciente),
    id_agravo VARCHAR(10) REFERENCES tb_agravo(id_cid),
    id_cnes_not VARCHAR(20) REFERENCES tb_unidade_saude(id_cnes),
    dt_notificacao DATE,
    sem_notificacao INTEGER,
    nu_ano INTEGER,
    tp_notificacao INTEGER,
    cs_suspeito VARCHAR(1)
);

-- =======================================================
-- 4. Tabela de Dados Clínicos
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_dados_clinicos (
    id_notificacao BIGINT PRIMARY KEY REFERENCES tb_notificacao(id_notificacao) ON DELETE CASCADE,
    dt_sin_pri DATE,
    sem_pri INTEGER,
    dt_investigacao DATE,
    dt_encerramento DATE,
    dt_obito DATE,
    classi_fin INTEGER,
    criterio INTEGER,
    doenca_trabalho INTEGER,
    evolucao INTEGER
);

-- CHECK constraints de domínio (barreira contra valores inválidos)
-- classi_fin: 0=Descartado 1=Confirmado 2=Em investigação 8=Inconclusivo
-- criterio:   0=Em investigação 1=Laboratorial 2=Clínico-epidemiológico
-- evolucao:   0=Em investigação 1=Cura 2=Óbito agravo 3=Óbito outra causa 9=Ignorado
-- NULL é permitido (campo não preenchido na ficha); o IN só barra valores fora do domínio.
ALTER TABLE tb_dados_clinicos
    ADD CONSTRAINT chk_classi_fin CHECK (classi_fin IS NULL OR classi_fin IN (0, 1, 2, 8)),
    ADD CONSTRAINT chk_criterio   CHECK (criterio   IS NULL OR criterio   IN (0, 1, 2)),
    ADD CONSTRAINT chk_evolucao   CHECK (evolucao   IS NULL OR evolucao   IN (0, 1, 2, 3, 9));

-- =======================================================
-- 5. Tabela de Geografia Epidemiológica
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_geografia_epidemiologica (
    id_notificacao BIGINT PRIMARY KEY REFERENCES tb_notificacao(id_notificacao) ON DELETE CASCADE,
    id_municipio_not INTEGER REFERENCES tb_municipio(id_municipio),
    id_municipio_resi INTEGER REFERENCES tb_municipio(id_municipio),
    id_municipio_inf INTEGER REFERENCES tb_municipio(id_municipio),
    id_pais_resi INTEGER REFERENCES tb_pais(id_pais),
    id_pais_inf INTEGER REFERENCES tb_pais(id_pais),
    tp_autoctonia INTEGER
);

-- =======================================================
-- 6. Tabela de Rastreabilidade do Sistema
--    OBS: cs_flxret/flxrecebi vêm como char no SINAN; mantidos INTEGER
--    pois o ETL faz a conversão. Documentado como observação.
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_sistema_rastreabilidade (
    id_notificacao BIGINT PRIMARY KEY REFERENCES tb_notificacao(id_notificacao) ON DELETE CASCADE,
    dt_digitacao DATE,
    nduplic_n INTEGER,
    in_vincula INTEGER,
    cs_flxret INTEGER,
    flxrecebi INTEGER,
    tp_sistema VARCHAR(20),
    arquivo_origem VARCHAR(50)
);

-- =======================================================
-- 7. Tabela de Auditoria JSONB
-- =======================================================
CREATE TABLE IF NOT EXISTS tb_auditoria (
    id_auditoria BIGSERIAL PRIMARY KEY,
    nome_tabela VARCHAR(50),
    id_registro BIGINT,
    tipo_operacao CHAR(1),
    dados_antigos JSONB,
    dados_novos JSONB,
    usuario_db VARCHAR(50),
    dt_auditoria TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =======================================================
-- 8. Índices de Performance Distribuídos
-- =======================================================
CREATE INDEX IF NOT EXISTS idx_clinicos_dtsinpri ON tb_dados_clinicos (dt_sin_pri);
CREATE INDEX IF NOT EXISTS idx_clinicos_classifin ON tb_dados_clinicos (classi_fin);
CREATE INDEX IF NOT EXISTS idx_notif_dtnotif ON tb_notificacao (dt_notificacao);
CREATE INDEX IF NOT EXISTS idx_notif_ano ON tb_notificacao (nu_ano);
CREATE INDEX IF NOT EXISTS idx_geo_munresi ON tb_geografia_epidemiologica (id_municipio_resi);
CREATE INDEX IF NOT EXISTS idx_paciente_idade ON tb_paciente (idade_anos);
CREATE INDEX IF NOT EXISTS idx_paciente_gestant ON tb_paciente (cs_gestant);
