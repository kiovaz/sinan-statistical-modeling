-- 04_seed_dimensoes.sql
-- Este script popula as tabelas de domínio estáticas (País, UFs e Agravos principais).
-- Municípios, Ocupações e Unidades de Saúde (CNES) geralmente são alimentados via script Python 
-- ou dump completo do IBGE devido ao alto volume de dados.

-- 1. Popula a tabela de Países (focando no Brasil que é o ID 1 no SINAN)
INSERT INTO tb_pais (id_pais, nm_pais) VALUES
(1, 'Brasil'),
(31, 'Argentina'),
(32, 'Bolívia'),
(42, 'Colômbia'),
(63, 'Estados Unidos'),
(99, 'Ignorado')
ON CONFLICT (id_pais) DO NOTHING;

-- 2. Popula a tabela de Agravos (Focando no Zika)
INSERT INTO tb_agravo (id_cid, nm_agravo) VALUES
('A92', 'Febre por vírus Zika (agravos gerais)'),
('A928', 'Outras febres virais especificadas transmitidas por mosquitos (Zika)'),
('A90', 'Dengue clássica'),
('A920', 'Doença pelo vírus Chikungunya')
ON CONFLICT (id_cid) DO NOTHING;

-- 3. Popula a tabela de Unidades Federativas (UFs)
INSERT INTO tb_uf (id_uf, sg_uf, nm_uf) VALUES
(11, 'RO', 'Rondônia'),
(12, 'AC', 'Acre'),
(13, 'AM', 'Amazonas'),
(14, 'RR', 'Roraima'),
(15, 'PA', 'Pará'),
(16, 'AP', 'Amapá'),
(17, 'TO', 'Tocantins'),
(21, 'MA', 'Maranhão'),
(22, 'PI', 'Piauí'),
(23, 'CE', 'Ceará'),
(24, 'RN', 'Rio Grande do Norte'),
(25, 'PB', 'Paraíba'),
(26, 'PE', 'Pernambuco'),
(27, 'AL', 'Alagoas'),
(28, 'SE', 'Sergipe'),
(29, 'BA', 'Bahia'),
(31, 'MG', 'Minas Gerais'),
(32, 'ES', 'Espírito Santo'),
(33, 'RJ', 'Rio de Janeiro'),
(35, 'SP', 'São Paulo'),
(41, 'PR', 'Paraná'),
(42, 'SC', 'Santa Catarina'),
(43, 'RS', 'Rio Grande do Sul'),
(50, 'MS', 'Mato Grosso do Sul'),
(51, 'MT', 'Mato Grosso'),
(52, 'GO', 'Goiás'),
(53, 'DF', 'Distrito Federal')
ON CONFLICT (id_uf) DO NOTHING;
