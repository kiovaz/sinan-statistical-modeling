-- 02_functions_triggers.sql
-- Funções e Triggers (Modelo Normalizado)
-- ===========================================================================
-- CORREÇÕES E ADIÇÕES NESTA VERSÃO:
--   [ROBUSTEZ] fn_log_auditoria usa to_jsonb(row) e extrai id de forma segura
--   [MÉDIA]    Auditoria estendida a tb_geografia_epidemiologica
--   [MÉDIA]    fn_resumo_epidemiologico retorna casos_descartados e taxa_letalidade
--   [ENUNCIADO] Validação clínica agora BLOQUEIA inconsistências (RAISE EXCEPTION)
--   [ENUNCIADO] fn_insere_notificacao_validada (inserção validada) — entrega 2
--   [ENUNCIADO] fn_detecta_duplicatas (detecção de duplicatas)     — entrega 2
-- ===========================================================================

-- ===========================================================================
-- 1. Função de decodificação de idade
--    NU_IDADE_N composto: 1º dígito = unidade (1=h,2=dia,3=mês,4=ano), resto = qtd
-- ===========================================================================
DROP FUNCTION IF EXISTS fn_decodifica_idade_anos(VARCHAR) CASCADE;
CREATE OR REPLACE FUNCTION fn_decodifica_idade_anos(nu_idade_n VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    unidade INTEGER;
    quantidade INTEGER;
BEGIN
    IF nu_idade_n IS NULL OR length(nu_idade_n) < 4 THEN
        RETURN NULL;
    END IF;

    unidade := cast(substring(nu_idade_n from 1 for 1) as INTEGER);
    quantidade := cast(substring(nu_idade_n from 2 for 3) as INTEGER);

    IF unidade = 4 THEN
        RETURN quantidade;          -- Anos
    ELSIF unidade IN (1, 2, 3) THEN
        RETURN 0;                   -- Menos de um ano (hora, dia, mês)
    ELSE
        RETURN NULL;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql;


-- ===========================================================================
-- 2. Trigger Genérica de Auditoria JSONB
--    Correção de robustez: extrai o id a partir do próprio JSONB da linha,
--    procurando as chaves de PK conhecidas. Se nenhuma existir, grava NULL
--    mas não quebra — e funciona para qualquer tabela futura.
-- ===========================================================================
CREATE OR REPLACE FUNCTION fn_log_auditoria()
RETURNS TRIGGER AS $$
DECLARE
    v_id_registro BIGINT;
    v_old JSONB;
    v_new JSONB;
    v_linha JSONB;
BEGIN
    v_old := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END;
    v_new := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END;
    v_linha := COALESCE(v_new, v_old);

    -- Resolve o id de forma genérica: tenta id_paciente, senão id_notificacao
    v_id_registro := COALESCE(
        (v_linha ->> 'id_paciente')::BIGINT,
        (v_linha ->> 'id_notificacao')::BIGINT
    );

    IF (TG_OP = 'DELETE') THEN
        INSERT INTO tb_auditoria (nome_tabela, id_registro, tipo_operacao, dados_antigos, usuario_db)
        VALUES (TG_TABLE_NAME, v_id_registro, 'D', v_old, current_user);
        RETURN OLD;
    ELSIF (TG_OP = 'UPDATE') THEN
        INSERT INTO tb_auditoria (nome_tabela, id_registro, tipo_operacao, dados_antigos, dados_novos, usuario_db)
        VALUES (TG_TABLE_NAME, v_id_registro, 'U', v_old, v_new, current_user);
        RETURN NEW;
    ELSIF (TG_OP = 'INSERT') THEN
        INSERT INTO tb_auditoria (nome_tabela, id_registro, tipo_operacao, dados_novos, usuario_db)
        VALUES (TG_TABLE_NAME, v_id_registro, 'I', v_new, current_user);
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Aplica auditoria nas tabelas principais (DROP antes p/ reexecução idempotente)
DROP TRIGGER IF EXISTS trg_audit_paciente   ON tb_paciente;
DROP TRIGGER IF EXISTS trg_audit_notificacao ON tb_notificacao;
DROP TRIGGER IF EXISTS trg_audit_clinicos    ON tb_dados_clinicos;
DROP TRIGGER IF EXISTS trg_audit_geografia   ON tb_geografia_epidemiologica;

CREATE TRIGGER trg_audit_paciente    AFTER INSERT OR UPDATE OR DELETE ON tb_paciente               FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();
CREATE TRIGGER trg_audit_notificacao AFTER INSERT OR UPDATE OR DELETE ON tb_notificacao            FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();
CREATE TRIGGER trg_audit_clinicos    AFTER INSERT OR UPDATE OR DELETE ON tb_dados_clinicos         FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();
-- NOVO: cobre alterações de município de infecção/residência/notificação
CREATE TRIGGER trg_audit_geografia   AFTER INSERT OR UPDATE OR DELETE ON tb_geografia_epidemiologica FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();


-- ===========================================================================
-- 3. Trigger de Validação Clínica (tb_dados_clinicos)
--    Enunciado pede consistência ANTES de persistir -> agora BLOQUEIA.
-- ===========================================================================
CREATE OR REPLACE FUNCTION fn_valida_dados_clinicos()
RETURNS TRIGGER AS $$
BEGIN
    -- Regra 1 (bloqueante): óbito (evolucao 2 ou 3) exige dt_obito preenchida.
    IF NEW.evolucao IN (2, 3) AND NEW.dt_obito IS NULL THEN
        RAISE EXCEPTION
            'Inconsistência clínica (id %): evolução indica óbito (cod %) mas dt_obito está vazia.',
            NEW.id_notificacao, NEW.evolucao;
    END IF;

    -- Regra 2 (bloqueante): se há dt_obito, a evolução não pode ser "Cura" (1).
    IF NEW.dt_obito IS NOT NULL AND NEW.evolucao = 1 THEN
        RAISE EXCEPTION
            'Inconsistência clínica (id %): há data de óbito mas evolução = Cura.',
            NEW.id_notificacao;
    END IF;

    -- Regra 3 (bloqueante): data de óbito não pode ser anterior aos primeiros sintomas.
    IF NEW.dt_obito IS NOT NULL AND NEW.dt_sin_pri IS NOT NULL
       AND NEW.dt_obito < NEW.dt_sin_pri THEN
        RAISE EXCEPTION
            'Inconsistência clínica (id %): dt_obito (%) anterior a dt_sin_pri (%).',
            NEW.id_notificacao, NEW.dt_obito, NEW.dt_sin_pri;
    END IF;

    -- Regra 4 (não bloqueante): encerramento antes da investigação é só aviso.
    IF NEW.dt_encerramento IS NOT NULL AND NEW.dt_investigacao IS NOT NULL
       AND NEW.dt_encerramento < NEW.dt_investigacao THEN
        RAISE NOTICE
            'Aviso (id %): encerramento anterior à investigação.', NEW.id_notificacao;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_valida_clinicos ON tb_dados_clinicos;
CREATE TRIGGER trg_valida_clinicos BEFORE INSERT OR UPDATE ON tb_dados_clinicos FOR EACH ROW EXECUTE FUNCTION fn_valida_dados_clinicos();


-- ===========================================================================
-- 4. Função: Resumo Epidemiológico por UF e Ano
--    Agora retorna também casos_descartados e taxa_letalidade (% sobre confirmados)
-- ===========================================================================
DROP FUNCTION IF EXISTS fn_resumo_epidemiologico(VARCHAR, INTEGER) CASCADE;
CREATE OR REPLACE FUNCTION fn_resumo_epidemiologico(p_uf VARCHAR, p_ano INTEGER)
RETURNS TABLE (
    total_notificacoes BIGINT,
    casos_confirmados  BIGINT,
    casos_descartados  BIGINT,
    obitos             BIGINT,
    taxa_letalidade_pct NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)                                                   AS total_notificacoes,
        COUNT(*) FILTER (WHERE c.classi_fin = 1)                   AS casos_confirmados,
        COUNT(*) FILTER (WHERE c.classi_fin = 0)                   AS casos_descartados,
        COUNT(*) FILTER (WHERE c.evolucao = 2)                     AS obitos,
        ROUND(
            COUNT(*) FILTER (WHERE c.evolucao = 2 AND c.classi_fin = 1) * 100.0
            / NULLIF(COUNT(*) FILTER (WHERE c.classi_fin = 1), 0)
        , 2)                                                       AS taxa_letalidade_pct
    FROM tb_notificacao n
    JOIN tb_dados_clinicos c            ON n.id_notificacao = c.id_notificacao
    JOIN tb_geografia_epidemiologica g  ON n.id_notificacao = g.id_notificacao
    JOIN tb_municipio m                 ON g.id_municipio_resi = m.id_municipio
    JOIN tb_uf u                        ON m.id_uf = u.id_uf
    WHERE u.sg_uf = p_uf AND n.nu_ano = p_ano;
END;
$$ LANGUAGE plpgsql;


-- ===========================================================================
-- 5. Função: Detecção de Duplicatas  (ENTREGA 2 / verificação pós-carga)
--    A base não tem identificador de pessoa, então a duplicidade é detectada
--    por CHAVE COMPOSTA de notificação:
--       agravo + data de sintomas + idade codificada + sexo
--       + município de residência + município de notificação
--    Uso: rodar APÓS a carga para auditar se sobrou alguma duplicata que o
--    ETL (staging) não removeu. Em base bem deduplicada, deve retornar 0 linhas.
-- ===========================================================================
DROP FUNCTION IF EXISTS fn_detecta_duplicatas() CASCADE;
CREATE OR REPLACE FUNCTION fn_detecta_duplicatas()
RETURNS TABLE (
    id_agravo         VARCHAR,
    dt_sin_pri        DATE,
    nu_idade_n        VARCHAR,
    cs_sexo           CHAR,
    id_municipio_resi INTEGER,
    id_municipio_not  INTEGER,
    qtd_registros     BIGINT,
    ids_notificacao   BIGINT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        n.id_agravo,
        c.dt_sin_pri,
        p.nu_idade_n,
        p.cs_sexo,
        g.id_municipio_resi,
        g.id_municipio_not,
        COUNT(*)                                              AS qtd_registros,
        array_agg(n.id_notificacao ORDER BY n.id_notificacao) AS ids_notificacao
    FROM tb_notificacao n
    JOIN tb_paciente p                  ON n.id_paciente = p.id_paciente
    JOIN tb_dados_clinicos c            ON n.id_notificacao = c.id_notificacao
    JOIN tb_geografia_epidemiologica g  ON n.id_notificacao = g.id_notificacao
    GROUP BY n.id_agravo, c.dt_sin_pri, p.nu_idade_n, p.cs_sexo,
             g.id_municipio_resi, g.id_municipio_not
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC;
END;
$$ LANGUAGE plpgsql;


-- ===========================================================================
-- 6. Função: Inserção Validada de Notificação  (ENTREGA 2)
--    Orquestra a inserção paciente -> notificacao -> clínicos -> geografia,
--    decodificando a idade e checando duplicidade pela CHAVE COMPOSTA antes
--    de persistir (a base não tem identificador de pessoa).
--    Retorna o id_notificacao criado, ou -1 se for considerada duplicata.
-- ===========================================================================
DROP FUNCTION IF EXISTS fn_insere_notificacao_validada(
    CHAR, VARCHAR, INTEGER, INTEGER, INTEGER, VARCHAR, INTEGER,
    DATE, DATE, INTEGER, INTEGER, INTEGER, INTEGER) CASCADE;
CREATE OR REPLACE FUNCTION fn_insere_notificacao_validada(
    p_cs_sexo       CHAR,
    p_nu_idade_n    VARCHAR,
    p_cs_gestant    INTEGER,
    p_cs_raca       INTEGER,
    p_cs_escol      INTEGER,
    p_id_agravo     VARCHAR,
    p_nu_ano        INTEGER,
    p_dt_notif      DATE,
    p_dt_sin_pri    DATE,
    p_classi_fin    INTEGER,
    p_evolucao      INTEGER,
    p_mun_resi      INTEGER,
    p_mun_not       INTEGER
)
RETURNS BIGINT AS $$
DECLARE
    v_id_paciente   BIGINT;
    v_id_notif      BIGINT;
    v_idade_anos    INTEGER;
    v_dup           BIGINT;
BEGIN
    -- 1. Checagem de duplicidade pela chave composta de notificação
    --    (agravo + sintomas + idade + sexo + município residência + notificação)
    SELECT COUNT(*) INTO v_dup
    FROM tb_notificacao n
    JOIN tb_paciente p                 ON n.id_paciente = p.id_paciente
    JOIN tb_dados_clinicos c           ON n.id_notificacao = c.id_notificacao
    JOIN tb_geografia_epidemiologica g ON n.id_notificacao = g.id_notificacao
    WHERE n.id_agravo = p_id_agravo
      AND c.dt_sin_pri IS NOT DISTINCT FROM p_dt_sin_pri
      AND p.nu_idade_n IS NOT DISTINCT FROM p_nu_idade_n
      AND p.cs_sexo    IS NOT DISTINCT FROM p_cs_sexo
      AND g.id_municipio_resi IS NOT DISTINCT FROM p_mun_resi
      AND g.id_municipio_not  IS NOT DISTINCT FROM p_mun_not;

    IF v_dup > 0 THEN
        RAISE NOTICE 'Notificação ignorada: duplicata provável (agravo %, sintomas %, idade %, sexo %, mun.resi %, mun.not %).',
            p_id_agravo, p_dt_sin_pri, p_nu_idade_n, p_cs_sexo, p_mun_resi, p_mun_not;
        RETURN -1;
    END IF;

    -- 2. Validação básica de domínio antes de persistir
    IF p_classi_fin IS NOT NULL AND p_classi_fin NOT IN (0, 1, 2, 8) THEN
        RAISE EXCEPTION 'classi_fin inválido: %', p_classi_fin;
    END IF;

    -- 3. Decodifica idade
    v_idade_anos := fn_decodifica_idade_anos(p_nu_idade_n);

    -- 4. Insere paciente
    INSERT INTO tb_paciente (cs_sexo, nu_idade_n, idade_anos, cs_gestant, cs_raca, cs_escolaridade)
    VALUES (p_cs_sexo, p_nu_idade_n, v_idade_anos, p_cs_gestant, p_cs_raca, p_cs_escol)
    RETURNING id_paciente INTO v_id_paciente;

    -- 5. Insere notificação
    INSERT INTO tb_notificacao (id_paciente, id_agravo, dt_notificacao, nu_ano, tp_notificacao)
    VALUES (v_id_paciente, p_id_agravo, p_dt_notif, p_nu_ano, 2)
    RETURNING id_notificacao INTO v_id_notif;

    -- 6. Insere dados clínicos (a trigger de validação clínica roda aqui)
    INSERT INTO tb_dados_clinicos (id_notificacao, dt_sin_pri, classi_fin, evolucao)
    VALUES (v_id_notif, p_dt_sin_pri, p_classi_fin, p_evolucao);

    -- 7. Insere geografia (necessária para a própria detecção de duplicidade)
    INSERT INTO tb_geografia_epidemiologica (id_notificacao, id_municipio_resi, id_municipio_not)
    VALUES (v_id_notif, p_mun_resi, p_mun_not);

    RETURN v_id_notif;
END;
$$ LANGUAGE plpgsql;
