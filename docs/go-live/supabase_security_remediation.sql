-- ============================================================================
-- Supabase Security-Remediation — Projekt qyrjeckzacjaazkpvnjk
-- STATUS: ⚠️ FREIGABE ERFORDERLICH — NICHT automatisch angewendet.
-- Grund: Live-DDL auf der Produktionsdatenbank. Vor dem Ausführen prüfen,
--        welche Anwendung das `api`-Schema tatsächlich per anon-Key nutzt
--        (sonst brechen legitime Frontend-Reads).
--
-- Befund (get_advisors, 2026-08-26): 221 Findings, davon
--   18x ERROR security_definer_view  — Views im `api`-Schema umgehen RLS
--    1x ERROR rls_disabled_in_public  — api.pipeline_results ohne RLS
--   85x WARN  anon-exposed            — `anon` darf api.*-Views SELECTen
--   84x WARN  authenticated-exposed
--    6x WARN  function_search_path_mutable
--    1x WARN  auth_leaked_password_protection (nur im Auth-Dashboard aktivierbar)
--   25x INFO  rls_enabled_no_policy
--
-- Betroffen sind u. a. Views mit personenbezogenen/Umsatzdaten:
--   api.ds24_purchases, api.leads, api.aiitec_contacts, api.aiitec_email_events,
--   api.aiitec_companies, api.mpo_companies, api.revenue_snapshots
-- ============================================================================

-- ----------------------------------------------------------------------------
-- SCHRITT 1 (empfohlen, minimal-invasiv): anon/authenticated den Zugriff auf
-- das gesamte api-Schema entziehen. Der service_role-Key (Backend) behält Zugriff.
-- Das schließt die Daten-Leak-Fläche sofort, ohne Views neu zu definieren.
-- ----------------------------------------------------------------------------
REVOKE USAGE ON SCHEMA api FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA api FROM anon, authenticated;  -- deckt SELECT + INSERT/UPDATE/DELETE/TRUNCATE (pipeline_results) ab
ALTER DEFAULT PRIVILEGES IN SCHEMA api REVOKE ALL ON TABLES FROM anon, authenticated;

-- Falls das api-Schema NICHT von einem legitimen Frontend gebraucht wird,
-- kann es alternativ ganz aus der PostgREST-Exposure entfernt werden
-- (Dashboard → Settings → API → "Exposed schemas": `api` entfernen).

-- ----------------------------------------------------------------------------
-- SCHRITT 2: RLS auf der einen ungeschützten Tabelle aktivieren.
-- ----------------------------------------------------------------------------
ALTER TABLE api.pipeline_results ENABLE ROW LEVEL SECURITY;
-- Danach passende Policy ergänzen oder Tabelle aus der API-Exposure nehmen.

-- ----------------------------------------------------------------------------
-- SCHRITT 3: function_search_path_mutable härten (verhindert search_path-Hijack).
-- ----------------------------------------------------------------------------
ALTER FUNCTION public.increment                     SET search_path = '';
ALTER FUNCTION public.update_updated_at             SET search_path = '';
ALTER FUNCTION public.update_updated_at_seo_content SET search_path = '';
ALTER FUNCTION public.get_mpo_stats                 SET search_path = '';
ALTER FUNCTION public.get_aiitec_outreach_stats     SET search_path = '';
ALTER FUNCTION public.cleanup_expired_locks         SET search_path = '';

-- ----------------------------------------------------------------------------
-- SCHRITT 4 (Auth-Setting, NICHT per SQL): Leaked-Password-Protection aktivieren
-- Dashboard → Authentication → Policies → "Leaked password protection" = ON.
-- ----------------------------------------------------------------------------

-- Nach dem Anwenden erneut `get_advisors(type=security)` laufen lassen und
-- verifizieren, dass die ERROR/WARN-Kategorien verschwunden sind.
