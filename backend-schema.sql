-- =============================================================
-- Backend Schema: New Tables for Dashboard Features
-- =============================================================
-- Run this in your Supabase SQL Editor after supabase_schema.sql
-- Covers: Templates Library, Compliance Tracker, Reply Threading,
--         Bulk Edit, Email Warmup Dashboard
-- =============================================================

-- ---------------------------------
-- 1. Email Templates Library
-- ---------------------------------
CREATE TABLE IF NOT EXISTS mail_agent_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  variables JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mail_agent_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can manage templates"
  ON mail_agent_templates FOR ALL
  USING (auth.role() = 'authenticated');

-- ---------------------------------
-- 2. Compliance Tracker
-- ---------------------------------
CREATE TABLE IF NOT EXISTS mail_agent_compliance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  name TEXT DEFAULT '',
  event_type TEXT NOT NULL CHECK (event_type IN ('unsubscribe', 'bounce', 'spam_complaint', 'gdpr_forget')),
  source TEXT DEFAULT '',
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compliance_email ON mail_agent_compliance(email);
CREATE INDEX IF NOT EXISTS idx_compliance_event_type ON mail_agent_compliance(event_type);
CREATE INDEX IF NOT EXISTS idx_compliance_created_at ON mail_agent_compliance(created_at);

ALTER TABLE mail_agent_compliance ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can manage compliance"
  ON mail_agent_compliance FOR ALL
  USING (auth.role() = 'authenticated');

-- ---------------------------------
-- 3. Threading Support: Add thread_id & is_reply to tracker
--    (only if they don't already exist)
-- ---------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'mail_agent_tracker' AND column_name = 'thread_id'
  ) THEN
    ALTER TABLE mail_agent_tracker ADD COLUMN thread_id TEXT DEFAULT '';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'mail_agent_tracker' AND column_name = 'is_reply'
  ) THEN
    ALTER TABLE mail_agent_tracker ADD COLUMN is_reply BOOLEAN DEFAULT FALSE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'mail_agent_tracker' AND column_name = 'reply_to_email'
  ) THEN
    ALTER TABLE mail_agent_tracker ADD COLUMN reply_to_email TEXT DEFAULT '';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'mail_agent_tracker' AND column_name = 'gmail_message_id'
  ) THEN
    ALTER TABLE mail_agent_tracker ADD COLUMN gmail_message_id TEXT DEFAULT '';
  END IF;
END $$;

-- ---------------------------------
-- 4. Campaign Management
-- ---------------------------------
CREATE TABLE IF NOT EXISTS mail_agent_campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'ARCHIVED')),
  target_audience TEXT DEFAULT '',
  total_leads INT DEFAULT 0,
  sent_count INT DEFAULT 0,
  reply_count INT DEFAULT 0,
  bounce_count INT DEFAULT 0,
  start_date TIMESTAMPTZ,
  end_date TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Add campaign_id to tracker
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'mail_agent_tracker' AND column_name = 'campaign_id'
  ) THEN
    ALTER TABLE mail_agent_tracker ADD COLUMN campaign_id UUID REFERENCES mail_agent_campaigns(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON mail_agent_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_tracker_campaign_id ON mail_agent_tracker(campaign_id);

ALTER TABLE mail_agent_campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can manage campaigns"
  ON mail_agent_campaigns FOR ALL
  USING (auth.role() = 'authenticated');

-- ---------------------------------
-- 5. Lead Notes & Activity Timeline
-- ---------------------------------
CREATE TABLE IF NOT EXISTS lead_notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id TEXT NOT NULL,
  note_text TEXT NOT NULL,
  note_type TEXT DEFAULT 'general' CHECK (note_type IN ('general', 'call', 'meeting', 'follow_up', 'research', 'other')),
  created_by TEXT DEFAULT 'user',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_notes_lead_id ON lead_notes(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_notes_created_at ON lead_notes(created_at);

ALTER TABLE lead_notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can manage lead notes"
  ON lead_notes FOR ALL
  USING (auth.role() = 'authenticated');

-- ---------------------------------
-- 6. Lead Scoring Table
-- ---------------------------------
CREATE TABLE IF NOT EXISTS lead_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id TEXT NOT NULL,
  company_name TEXT DEFAULT '',
  score FLOAT DEFAULT 0,
  reasoning TEXT DEFAULT '',
  scored_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_scores_lead_id ON lead_scores(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_scores_scored_at ON lead_scores(scored_at);

ALTER TABLE lead_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can manage lead scores"
  ON lead_scores FOR ALL
  USING (auth.role() = 'authenticated');
