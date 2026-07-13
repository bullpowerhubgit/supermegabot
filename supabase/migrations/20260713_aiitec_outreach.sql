-- AIITEC B2B Outreach Machine — Supabase Schema
-- Ausführen via: Supabase Dashboard → SQL Editor

CREATE TABLE IF NOT EXISTS aiitec_companies (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    domain        TEXT,
    email         TEXT NOT NULL UNIQUE,
    branche       TEXT,
    umsatzklasse  TEXT,
    land          TEXT DEFAULT 'DE',
    track         TEXT,
    product_key   TEXT,
    status        TEXT DEFAULT 'new',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiitec_contacts (
    id            BIGSERIAL PRIMARY KEY,
    company_id    BIGINT REFERENCES aiitec_companies(id),
    name          TEXT,
    rolle         TEXT,
    email         TEXT NOT NULL UNIQUE,
    opt_out       BOOLEAN DEFAULT FALSE,
    source        TEXT DEFAULT 'seed',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiitec_campaigns (
    id            BIGSERIAL PRIMARY KEY,
    company_id    BIGINT REFERENCES aiitec_companies(id),
    track         TEXT,
    product_key   TEXT,
    stage         INTEGER DEFAULT 1,
    sent_at       TIMESTAMPTZ,
    subject       TEXT,
    status        TEXT DEFAULT 'queued',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiitec_email_events (
    id            BIGSERIAL PRIMARY KEY,
    campaign_id   BIGINT REFERENCES aiitec_campaigns(id),
    event_type    TEXT,
    detail        TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_aiitec_companies_status ON aiitec_companies(status);
CREATE INDEX IF NOT EXISTS idx_aiitec_companies_track  ON aiitec_companies(track);
CREATE INDEX IF NOT EXISTS idx_aiitec_campaigns_stage  ON aiitec_campaigns(stage, status);
CREATE INDEX IF NOT EXISTS idx_aiitec_campaigns_sent   ON aiitec_campaigns(sent_at);

-- RLS
ALTER TABLE aiitec_companies    ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiitec_contacts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiitec_campaigns    ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiitec_email_events ENABLE ROW LEVEL SECURITY;

-- Service Role Bypass (für Backend)
CREATE POLICY "service_role_all_companies"    ON aiitec_companies    USING (auth.role() = 'service_role');
CREATE POLICY "service_role_all_contacts"     ON aiitec_contacts     USING (auth.role() = 'service_role');
CREATE POLICY "service_role_all_campaigns"    ON aiitec_campaigns    USING (auth.role() = 'service_role');
CREATE POLICY "service_role_all_events"       ON aiitec_email_events USING (auth.role() = 'service_role');
