-- 02_functions_triggers.sql
-- Funções e Triggers (Modelo Normalizado)

-- 1. Função de decodificação de idade
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
        RETURN quantidade; -- Anos
    ELSIF unidade IN (1, 2, 3) THEN
        RETURN 0; -- Menos de um ano (hora, dia, mês)
    ELSE
        RETURN NULL;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql;


-- 2. Trigger Genérica de Auditoria JSONB
CREATE OR REPLACE FUNCTION fn_log_auditoria() 
RETURNS TRIGGER AS $$
DECLARE
    v_id_registro BIGINT;
BEGIN
    -- Identifica o ID dependendo da tabela
    IF (TG_TABLE_NAME = 'tb_paciente') THEN
        v_id_registro := COALESCE(NEW.id_paciente, OLD.id_paciente);
    ELSE
        v_id_registro := COALESCE(NEW.id_notificacao, OLD.id_notificacao);
    END IF;

    IF (TG_OP = 'DELETE') THEN
        INSERT INTO tb_auditoria (nome_tabela, id_registro, tipo_operacao, dados_antigos, usuario_db)
        VALUES (TG_TABLE_NAME, v_id_registro, 'D', row_to_json(OLD)::jsonb, current_user);
        RETURN OLD;
    ELSIF (TG_OP = 'UPDATE') THEN
        INSERT INTO tb_auditoria (nome_tabela, id_registro, tipo_operacao, dados_antigos, dados_novos, usuario_db)
        VALUES (TG_TABLE_NAME, v_id_registro, 'U', row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb, current_user);
        RETURN NEW;
    ELSIF (TG_OP = 'INSERT') THEN
        INSERT INTO tb_auditoria (nome_tabela, id_registro, tipo_operacao, dados_novos, usuario_db)
        VALUES (TG_TABLE_NAME, v_id_registro, 'I', row_to_json(NEW)::jsonb, current_user);
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Aplica auditoria nas tabelas principais
CREATE TRIGGER trg_audit_paciente AFTER INSERT OR UPDATE OR DELETE ON tb_paciente FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();
CREATE TRIGGER trg_audit_notificacao AFTER INSERT OR UPDATE OR DELETE ON tb_notificacao FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();
CREATE TRIGGER trg_audit_clinicos AFTER INSERT OR UPDATE OR DELETE ON tb_dados_clinicos FOR EACH ROW EXECUTE FUNCTION fn_log_auditoria();


-- 3. Trigger de Validação Clínica (tb_dados_clinicos)
CREATE OR REPLACE FUNCTION fn_valida_dados_clinicos() 
RETURNS TRIGGER AS $$
BEGIN
    -- Validação: se evolucao = 2 (Óbito pelo agravo) ou 3 (Óbito por outra causa), dt_obito deve estar preenchida
    IF NEW.evolucao IN (2, 3) AND NEW.dt_obito IS NULL THEN
        RAISE NOTICE 'Aviso: Evolução indica óbito, mas a data do óbito não foi informada na tb_dados_clinicos para o ID %.', NEW.id_notificacao;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_valida_clinicos BEFORE INSERT OR UPDATE ON tb_dados_clinicos FOR EACH ROW EXECUTE FUNCTION fn_valida_dados_clinicos();


-- 4. Função: Resumo Epidemiológico por UF e Ano (Agora usando JOINs normalizados)
CREATE OR REPLACE FUNCTION fn_resumo_epidemiologico(p_uf VARCHAR, p_ano INTEGER)
RETURNS TABLE (
    total_notificacoes BIGINT,
    casos_confirmados BIGINT,
    obitos BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*) AS total_notificacoes,
        SUM(CASE WHEN c.classi_fin = 1 THEN 1 ELSE 0 END) AS casos_confirmados,
        SUM(CASE WHEN c.evolucao = 2 THEN 1 ELSE 0 END) AS obitos
    FROM tb_notificacao n
    JOIN tb_dados_clinicos c ON n.id_notificacao = c.id_notificacao
    JOIN tb_geografia_epidemiologica g ON n.id_notificacao = g.id_notificacao
    JOIN tb_municipio m ON g.id_municipio_resi = m.id_municipio
    JOIN tb_uf u ON m.id_uf = u.id_uf
    WHERE u.sg_uf = p_uf AND n.nu_ano = p_ano;
END;
$$ LANGUAGE plpgsql;
