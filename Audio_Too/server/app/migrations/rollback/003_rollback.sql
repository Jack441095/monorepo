-- Revert CRM tables and automix_jobs schema by removing optimistic versioning and worker columns
PRAGMA foreign_keys=OFF;

-- Recreate automix_jobs
CREATE TABLE IF NOT EXISTS automix_jobs_old (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    status TEXT,
    genre TEXT,
    style_prefs TEXT,
    error_message TEXT,
    result_path TEXT,
    iteration_count INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
);
INSERT OR IGNORE INTO automix_jobs_old (id, project_id, status, genre, style_prefs, error_message, result_path, iteration_count, created_at, updated_at)
SELECT id, project_id, status, genre, style_prefs, error_message, result_path, iteration_count, created_at, updated_at FROM automix_jobs;
DROP TABLE IF EXISTS automix_jobs;
ALTER TABLE automix_jobs_old RENAME TO automix_jobs;

-- Recreate enquiries
CREATE TABLE IF NOT EXISTS enquiries_old (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    service TEXT,
    message TEXT,
    deadline TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
INSERT OR IGNORE INTO enquiries_old (id, name, email, service, message, deadline, status, created_at, updated_at)
SELECT id, name, email, service, message, deadline, status, created_at, updated_at FROM enquiries;
DROP TABLE IF EXISTS enquiries;
ALTER TABLE enquiries_old RENAME TO enquiries;

-- Recreate projects
CREATE TABLE IF NOT EXISTS projects_old (
    id TEXT PRIMARY KEY,
    client TEXT,
    project TEXT,
    service TEXT,
    status TEXT,
    deadline TEXT,
    waiting_on TEXT,
    follow_up TEXT,
    next_action TEXT,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
);
INSERT OR IGNORE INTO projects_old (id, client, project, service, status, deadline, waiting_on, follow_up, next_action, source, created_at, updated_at)
SELECT id, client, project, service, status, deadline, waiting_on, follow_up, next_action, source, created_at, updated_at FROM projects;
DROP TABLE IF EXISTS projects;
ALTER TABLE projects_old RENAME TO projects;

-- Recreate clients
CREATE TABLE IF NOT EXISTS clients_old (
    id TEXT PRIMARY KEY,
    name TEXT,
    contact TEXT,
    status TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);
INSERT OR IGNORE INTO clients_old (id, name, contact, status, notes, created_at, updated_at)
SELECT id, name, contact, status, notes, created_at, updated_at FROM clients;
DROP TABLE IF EXISTS clients;
ALTER TABLE clients_old RENAME TO clients;

-- Recreate leads
CREATE TABLE IF NOT EXISTS leads_old (
    id TEXT PRIMARY KEY,
    lead TEXT,
    contact TEXT,
    type TEXT,
    service_fit TEXT,
    status TEXT,
    score REAL,
    source TEXT,
    next_action TEXT,
    waiting_on TEXT,
    follow_up TEXT,
    created_at TEXT,
    updated_at TEXT
);
INSERT OR IGNORE INTO leads_old (id, lead, contact, type, service_fit, status, score, source, next_action, waiting_on, follow_up, created_at, updated_at)
SELECT id, lead, contact, type, service_fit, status, score, source, next_action, waiting_on, follow_up, created_at, updated_at FROM leads;
DROP TABLE IF EXISTS leads;
ALTER TABLE leads_old RENAME TO leads;

-- Recreate invoices
CREATE TABLE IF NOT EXISTS invoices_old (
    id TEXT PRIMARY KEY,
    date TEXT,
    client TEXT,
    service TEXT,
    hours REAL,
    rate REAL,
    total REAL,
    status TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(client) REFERENCES clients(id) ON DELETE SET NULL
);
INSERT OR IGNORE INTO invoices_old (id, date, client, service, hours, rate, total, status, notes, created_at, updated_at)
SELECT id, date, client, service, hours, rate, total, status, notes, created_at, updated_at FROM invoices;
DROP TABLE IF EXISTS invoices;
ALTER TABLE invoices_old RENAME TO invoices;

-- Recreate drafts
CREATE TABLE IF NOT EXISTS drafts_old (
    id TEXT PRIMARY KEY,
    type TEXT,
    recipient TEXT,
    subject TEXT,
    body TEXT,
    status TEXT,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
);
INSERT OR IGNORE INTO drafts_old (id, type, recipient, subject, body, status, source, created_at, updated_at)
SELECT id, type, recipient, subject, body, status, source, created_at, updated_at FROM drafts;
DROP TABLE IF EXISTS drafts;
ALTER TABLE drafts_old RENAME TO drafts;

PRAGMA foreign_keys=ON;
