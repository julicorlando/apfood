-- =============================================================================
-- Restrições que o Prisma não expressa no schema. Aplicadas por uma migration
-- manual logo após a migration inicial (pnpm db:migrate cria a pasta; copie
-- este conteúdo para uma migration "extras" ou rode `pnpm db:extras`).
-- =============================================================================

-- No máximo 1 turno ABERTO por operador.
CREATE UNIQUE INDEX IF NOT EXISTS turno_aberto_por_usuario
  ON turnos_caixa (usuario_id)
  WHERE status = 'ABERTO';

-- Valores monetários nunca negativos (o sinal vem do tipo da movimentação).
ALTER TABLE movimentacoes_caixa
  ADD CONSTRAINT movimentacoes_caixa_valor_positivo CHECK (valor_centavos > 0);

ALTER TABLE pagamentos
  ADD CONSTRAINT pagamentos_valor_positivo CHECK (valor_centavos > 0),
  ADD CONSTRAINT pagamentos_troco_nao_negativo CHECK (troco_centavos >= 0);

ALTER TABLE pedidos
  ADD CONSTRAINT pedidos_total_nao_negativo CHECK (total_centavos >= 0);

ALTER TABLE itens_pedido
  ADD CONSTRAINT itens_pedido_quantidade_positiva CHECK (quantidade > 0);

ALTER TABLE grupos_adicionais
  ADD CONSTRAINT grupos_adicionais_min_max CHECK (min_selecao >= 0 AND max_selecao >= min_selecao);

-- Busca de cliente por telefone parcial no delivery (ex.: últimos dígitos).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS clientes_telefone_trgm
  ON clientes USING gin (telefone gin_trgm_ops);
