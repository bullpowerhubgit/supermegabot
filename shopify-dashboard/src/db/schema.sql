-- ============================================
-- SHOPIFY DASHBOARD DB SCHEMA
-- Supabase PostgreSQL with RLS
-- ============================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table (linked to Supabase Auth)
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free','starter','pro','enterprise')),
  plan_status TEXT NOT NULL DEFAULT 'active' CHECK (plan_status IN ('active','cancelled','past_due')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Shops table (Shopify store credentials)
CREATE TABLE IF NOT EXISTS shops (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  shop_domain TEXT UNIQUE NOT NULL,
  access_token TEXT NOT NULL,
  installed_at TIMESTAMPTZ DEFAULT now(),
  subscription_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Usage tracking
CREATE TABLE IF NOT EXISTS usage_daily (
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  metric TEXT NOT NULL,
  date DATE NOT NULL DEFAULT CURRENT_DATE,
  count INTEGER DEFAULT 0,
  PRIMARY KEY (user_id, metric, date)
);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource TEXT NOT NULL,
  details JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE shops ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY users_self ON users FOR ALL USING (auth.uid() = id);
CREATE POLICY shops_owner ON shops FOR ALL USING (auth.uid() = user_id);
CREATE POLICY usage_owner ON usage_daily FOR ALL USING (auth.uid() = user_id);
CREATE POLICY audit_owner ON audit_log FOR ALL USING (auth.uid() = user_id);

-- Indexes
CREATE INDEX idx_shops_user_id ON shops(user_id);
CREATE INDEX idx_usage_user_metric_date ON usage_daily(user_id, metric, date);
CREATE INDEX idx_audit_user_id ON audit_log(user_id_id);
CREATE INDEX idx_audit_created ON audit_log(created_at);

-- Updated at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
