-- ============================================================
-- Incident Platform — PostgreSQL schema
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create schemas for each service
CREATE SCHEMA IF NOT EXISTS alerts;
CREATE SCHEMA IF NOT EXISTS incidents;
CREATE SCHEMA IF NOT EXISTS oncall;
CREATE SCHEMA IF NOT EXISTS notifications;

-- ── ENUM types ──────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE severity_level AS ENUM ('critical', 'high', 'medium', 'low', 'info');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE alert_status AS ENUM ('firing', 'acknowledged', 'resolved');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE incident_status AS ENUM (
        'open', 'acknowledged', 'in_progress',
        'investigating', 'mitigated', 'resolved', 'closed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('admin', 'responder', 'viewer');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE alert_event_type AS ENUM (
        'created', 'acknowledged', 'escalated', 'resolved', 'suppressed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE notification_channel AS ENUM ('email', 'sms', 'slack', 'pagerduty');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE notification_status AS ENUM ('sent', 'delivered', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── Users (public schema) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT        NOT NULL,
    email       TEXT        NOT NULL UNIQUE,
    phone       TEXT,
    role        user_role   NOT NULL DEFAULT 'responder',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Alerts schema tables ────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts.alerts (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id      VARCHAR(255) UNIQUE NOT NULL,
    external_id   TEXT,
    source        TEXT,
    service       VARCHAR(255) NOT NULL,
    severity      severity_level NOT NULL,
    status        alert_status   NOT NULL DEFAULT 'firing',
    title         TEXT,
    message       TEXT NOT NULL,
    description   TEXT,
    labels        JSONB          NOT NULL DEFAULT '{}',
    annotations   JSONB          NOT NULL DEFAULT '{}',
    fingerprint   TEXT,
    fired_at      TIMESTAMPTZ,
    resolved_at   TIMESTAMPTZ,
    incident_id   UUID,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alerts_service_severity ON alerts.alerts(service, severity);
CREATE INDEX IF NOT EXISTS idx_alerts_status           ON alerts.alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_fingerprint      ON alerts.alerts(fingerprint);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp        ON alerts.alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_incident_id      ON alerts.alerts(incident_id);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at       ON alerts.alerts(created_at);

-- ── Alert Events (audit log) ────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts.alert_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id    UUID             NOT NULL REFERENCES alerts.alerts(id) ON DELETE CASCADE,
    event_type  alert_event_type NOT NULL,
    payload     JSONB            NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alert_events_alert ON alerts.alert_events(alert_id);

-- ── Incidents schema tables ─────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents.incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     VARCHAR(255) UNIQUE NOT NULL,
    title           VARCHAR(500) NOT NULL,
    description     TEXT,
    service         VARCHAR(255) NOT NULL,
    severity        severity_level  NOT NULL,
    status          incident_status NOT NULL DEFAULT 'open',
    assigned_to     TEXT,
    notes           JSONB           NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status   ON incidents.incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_service  ON incidents.incidents(service);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents.incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created  ON incidents.incidents(created_at);

-- ── Incident <-> Alerts (many-to-many) ────────────────────────
CREATE TABLE IF NOT EXISTS incidents.incident_alerts (
    incident_id UUID NOT NULL REFERENCES incidents.incidents(id) ON DELETE CASCADE,
    alert_id    UUID NOT NULL REFERENCES alerts.alerts(id)       ON DELETE CASCADE,
    linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (incident_id, alert_id)
);

-- ── Notification Log ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents.notification_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id    UUID REFERENCES alerts.alerts(id),
    incident_id UUID REFERENCES incidents.incidents(id),
    user_id     UUID NOT NULL REFERENCES users(id),
    channel     notification_channel NOT NULL,
    status      notification_status  NOT NULL DEFAULT 'sent',
    sent_at     TIMESTAMPTZ          NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_alert    ON incidents.notification_log(alert_id);
CREATE INDEX IF NOT EXISTS idx_notif_incident ON incidents.notification_log(incident_id);

-- ── Notifications schema (notification-service) ─────────────
CREATE TABLE IF NOT EXISTS notifications.notifications (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    notification_id  VARCHAR(255) UNIQUE NOT NULL,
    incident_id      VARCHAR(255) NOT NULL,
    engineer         VARCHAR(255) NOT NULL,
    channel          VARCHAR(50)  NOT NULL DEFAULT 'mock',
    status           VARCHAR(50)  NOT NULL DEFAULT 'sent',
    message          TEXT         NOT NULL,
    webhook_url      TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_incident  ON notifications.notifications(incident_id);
CREATE INDEX IF NOT EXISTS idx_notifications_channel   ON notifications.notifications(channel);
CREATE INDEX IF NOT EXISTS idx_notifications_created   ON notifications.notifications(created_at);

-- ── On-call schema tables ───────────────────────────────────
CREATE TABLE IF NOT EXISTS oncall.schedules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team                VARCHAR(255) NOT NULL,
    rotation_type       VARCHAR(50)  NOT NULL,
    start_date          DATE         NOT NULL,
    engineers           JSONB        NOT NULL,
    escalation_minutes  INTEGER      DEFAULT 5,
    handoff_hour        INTEGER      DEFAULT 9,
    timezone            VARCHAR(50)  DEFAULT 'UTC',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── Schedule Members (normalised member list with position) ──
CREATE TABLE IF NOT EXISTS oncall.schedule_members (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id UUID         NOT NULL REFERENCES oncall.schedules(id) ON DELETE CASCADE,
    user_name   VARCHAR(255) NOT NULL,
    user_email  VARCHAR(255) NOT NULL,
    position    INTEGER      NOT NULL,
    is_active   BOOLEAN      DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (schedule_id, position)
);

CREATE INDEX IF NOT EXISTS idx_schedule_members_schedule ON oncall.schedule_members(schedule_id);

CREATE TABLE IF NOT EXISTS oncall.oncall_assignments (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_name   TEXT NOT NULL,
    user_id     UUID NOT NULL REFERENCES users(id),
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oncall_team ON oncall.oncall_assignments(team_name);
CREATE INDEX IF NOT EXISTS idx_oncall_time ON oncall.oncall_assignments(start_time, end_time);

CREATE TABLE IF NOT EXISTS oncall.escalations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     VARCHAR(255) NOT NULL,
    from_engineer   VARCHAR(255) NOT NULL,
    to_engineer     VARCHAR(255) NOT NULL,
    level           INTEGER      NOT NULL DEFAULT 1,
    reason          VARCHAR(255),
    escalated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_escalations_incident ON oncall.escalations(incident_id);

-- ── Escalation Policies ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS oncall.escalation_policies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team            VARCHAR(255) NOT NULL,
    level           INTEGER      NOT NULL,
    wait_minutes    INTEGER      NOT NULL DEFAULT 5,
    notify_target   VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (team, level)
);

CREATE INDEX IF NOT EXISTS idx_escalation_policies_team ON oncall.escalation_policies(team);

-- ── Escalation Timers (active pending escalations) ──────────
CREATE TABLE IF NOT EXISTS oncall.escalation_timers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     VARCHAR(255) NOT NULL,
    team            VARCHAR(255) NOT NULL,
    current_level   INTEGER      NOT NULL DEFAULT 1,
    assigned_to     VARCHAR(255) NOT NULL,
    escalate_after  TIMESTAMPTZ  NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_escalation_timers_active ON oncall.escalation_timers(is_active, escalate_after);

-- ── Auto-update updated_at trigger ──────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alerts_updated_at    ON alerts.alerts;
DROP TRIGGER IF EXISTS trg_incidents_updated_at ON incidents.incidents;

CREATE TRIGGER trg_alerts_updated_at
    BEFORE UPDATE ON alerts.alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_incidents_updated_at
    BEFORE UPDATE ON incidents.incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Seed data ───────────────────────────────────────────────

-- Single user for the platform
INSERT INTO users (name, email, phone, role)
VALUES
    ('Omar Afidi', 'omarafidi2005@gmail.com', '+1-555-0100', 'admin')
ON CONFLICT (email) DO NOTHING;

-- On-call schedule for payment-api
INSERT INTO oncall.schedules (team, rotation_type, start_date, engineers, escalation_minutes, handoff_hour, timezone)
VALUES 
    (
        'payment-api',
        'weekly',
        '2026-02-01',
        '[
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": true}
        ]'::jsonb,
        5,
        9,
        'UTC'
    )
ON CONFLICT DO NOTHING;

-- Seed schedule_members
INSERT INTO oncall.schedule_members (schedule_id, user_name, user_email, position)
SELECT s.id, 'Omar Afidi', 'omarafidi2005@gmail.com', 1
FROM oncall.schedules s WHERE s.team = 'payment-api'
ON CONFLICT DO NOTHING;

-- Escalation policy
INSERT INTO oncall.escalation_policies (team, level, wait_minutes, notify_target)
VALUES
    ('payment-api', 1, 5, 'secondary'),
    ('payment-api', 2, 10, 'omarafidi2005@gmail.com')
ON CONFLICT DO NOTHING;

-- ============================================================
-- SCHEMA: analysis  (AI-powered alert analysis)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS analysis;

CREATE TABLE IF NOT EXISTS analysis.suggestions (
    suggestion_id   SERIAL PRIMARY KEY,
    alert_id        VARCHAR(255),
    incident_id     VARCHAR(255),
    alert_message   TEXT NOT NULL,
    alert_service   VARCHAR(200),
    alert_severity  VARCHAR(20),
    root_cause      TEXT NOT NULL,
    solution        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0,
    source          VARCHAR(50) NOT NULL DEFAULT 'knowledge_base',
    matched_pattern TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_suggestions_alert_id    ON analysis.suggestions(alert_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_incident_id ON analysis.suggestions(incident_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_created_at  ON analysis.suggestions(created_at DESC);

CREATE TABLE IF NOT EXISTS analysis.resolved_patterns (
    pattern_id      SERIAL PRIMARY KEY,
    service         VARCHAR(200),
    severity        VARCHAR(20),
    message_pattern TEXT NOT NULL,
    root_cause      TEXT NOT NULL,
    solution        TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resolved_patterns_service ON analysis.resolved_patterns(service);

-- ── Previous Incident 1: Auth-service outage (resolved, 3 alerts) ────
INSERT INTO incidents.incidents (incident_id, title, description, service, severity, status, assigned_to, created_at, acknowledged_at, resolved_at, updated_at)
VALUES
    ('inc-prev-1', '[CRITICAL] auth-service: Authentication failures', 'Multiple auth failures across production', 'auth-service', 'critical', 'resolved', 'Omar Afidi', NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days' + INTERVAL '2 minutes', NOW() - INTERVAL '3 days' + INTERVAL '45 minutes', NOW() - INTERVAL '3 days' + INTERVAL '45 minutes')
ON CONFLICT (incident_id) DO NOTHING;

INSERT INTO alerts.alerts (alert_id, service, severity, message, labels, timestamp, incident_id, status)
VALUES
    ('alert-prev-1a', 'auth-service', 'critical', 'Authentication endpoint returning 503. Login success rate dropped to 12%.', '{"env":"production"}', NOW() - INTERVAL '3 days', (SELECT id FROM incidents.incidents WHERE incident_id = 'inc-prev-1'), 'resolved'),
    ('alert-prev-1b', 'auth-service', 'critical', 'Token validation failures spiking: 850 errors/min. JWT verification timeout.', '{"env":"production"}', NOW() - INTERVAL '3 days' + INTERVAL '3 minutes', (SELECT id FROM incidents.incidents WHERE incident_id = 'inc-prev-1'), 'resolved'),
    ('alert-prev-1c', 'auth-service', 'critical', 'Redis session store unreachable from auth-service pods. Connection pool exhausted.', '{"env":"production"}', NOW() - INTERVAL '3 days' + INTERVAL '7 minutes', (SELECT id FROM incidents.incidents WHERE incident_id = 'inc-prev-1'), 'resolved')
ON CONFLICT (alert_id) DO NOTHING;

INSERT INTO incidents.incident_alerts (incident_id, alert_id)
SELECT i.id, a.id FROM incidents.incidents i, alerts.alerts a
WHERE i.incident_id = 'inc-prev-1' AND a.alert_id IN ('alert-prev-1a', 'alert-prev-1b', 'alert-prev-1c')
ON CONFLICT DO NOTHING;

-- ── Previous Incident 2: Order-service degradation (resolved, 3 alerts) ────
INSERT INTO incidents.incidents (incident_id, title, description, service, severity, status, assigned_to, created_at, acknowledged_at, resolved_at, updated_at)
VALUES
    ('inc-prev-2', '[HIGH] order-service: Order processing delays', 'Order pipeline backed up due to downstream timeout', 'order-service', 'high', 'resolved', 'Omar Afidi', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day' + INTERVAL '4 minutes', NOW() - INTERVAL '1 day' + INTERVAL '30 minutes', NOW() - INTERVAL '1 day' + INTERVAL '30 minutes')
ON CONFLICT (incident_id) DO NOTHING;

INSERT INTO alerts.alerts (alert_id, service, severity, message, labels, timestamp, incident_id, status)
VALUES
    ('alert-prev-2a', 'order-service', 'high', 'Order processing latency P99 at 12s. Queue depth growing: 8,200 pending orders.', '{"env":"production"}', NOW() - INTERVAL '1 day', (SELECT id FROM incidents.incidents WHERE incident_id = 'inc-prev-2'), 'resolved'),
    ('alert-prev-2b', 'order-service', 'high', 'Downstream inventory-service returning 504 Gateway Timeout. Retry budget exhausted.', '{"env":"production"}', NOW() - INTERVAL '1 day' + INTERVAL '5 minutes', (SELECT id FROM incidents.incidents WHERE incident_id = 'inc-prev-2'), 'resolved'),
    ('alert-prev-2c', 'order-service', 'high', 'Dead letter queue filling up: 340 failed order events in last 15 minutes.', '{"env":"production"}', NOW() - INTERVAL '1 day' + INTERVAL '10 minutes', (SELECT id FROM incidents.incidents WHERE incident_id = 'inc-prev-2'), 'resolved')
ON CONFLICT (alert_id) DO NOTHING;

INSERT INTO incidents.incident_alerts (incident_id, alert_id)
SELECT i.id, a.id FROM incidents.incidents i, alerts.alerts a
WHERE i.incident_id = 'inc-prev-2' AND a.alert_id IN ('alert-prev-2a', 'alert-prev-2b', 'alert-prev-2c')
ON CONFLICT DO NOTHING;