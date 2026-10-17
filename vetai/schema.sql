-- VETAI Proposal Studio — схема базы данных (SQLite).
-- Соответствует docs/ARCHITECTURE.md, раздел 3 «Схема данных».
-- Применяется идемпотентно (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS briefs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client      TEXT NOT NULL,
    task        TEXT NOT NULL,
    services    TEXT NOT NULL,              -- JSON-массив названий услуг
    deadlines   TEXT NOT NULL,
    budget      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id        INTEGER NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    current_version INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposal_versions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id         INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    version             INTEGER NOT NULL,
    status              TEXT NOT NULL
                        CHECK (status IN ('generated', 'edited', 'exported')),
    body                TEXT NOT NULL DEFAULT '',
    commercial_snapshot TEXT,               -- JSON доверенных цен/услуг (REQ-12)
    created_at          TEXT NOT NULL,
    UNIQUE (proposal_id, version)
);

CREATE TABLE IF NOT EXISTS price_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    price      INTEGER NOT NULL,            -- цена в КОПЕЙКАХ (целое, без float)
    is_active  INTEGER NOT NULL DEFAULT 1   -- 1 — в прайсе, 0 — архив
);

CREATE TABLE IF NOT EXISTS templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    structure  TEXT NOT NULL,               -- JSON-описание разделов (REQ-07)
    is_active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS generation_logs (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_version_id  INTEGER REFERENCES proposal_versions(id) ON DELETE SET NULL,
    provider             TEXT NOT NULL,
    prompt               TEXT NOT NULL,     -- без персональных данных (REQ-31)
    response             TEXT NOT NULL,     -- без персональных данных (REQ-31)
    status               TEXT NOT NULL,     -- ok / timeout / rate_limit / empty / error
    created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_briefs_updated_at ON briefs(updated_at);
CREATE INDEX IF NOT EXISTS idx_proposals_brief_id ON proposals(brief_id);
CREATE INDEX IF NOT EXISTS idx_versions_proposal_id ON proposal_versions(proposal_id);
