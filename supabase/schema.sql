-- Schema opcional. O app também cria estas tabelas automaticamente.

CREATE TABLE IF NOT EXISTS runs (
    id BIGSERIAL PRIMARY KEY,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    scope TEXT,
    level TEXT,
    profile TEXT,
    quantity INTEGER,
    max_categories INTEGER,
    apps_scanned INTEGER DEFAULT 0,
    apps_kept INTEGER DEFAULT 0,
    categories_done INTEGER DEFAULT 0,
    categories_total INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    last_message TEXT,
    config_json TEXT,
    output_dir TEXT,
    html_path TEXT,
    json_path TEXT,
    csv_path TEXT
);
CREATE TABLE IF NOT EXISTS apps (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL,
    categoria TEXT, categoria_codigo TEXT, rank INTEGER, app_id TEXT, title TEXT, developer TEXT,
    developer_email TEXT, developer_website TEXT, developer_address TEXT, privacy_policy TEXT,
    genre TEXT, genre_id TEXT, score DOUBLE PRECISION, ratings BIGINT, reviews BIGINT, installs TEXT,
    min_installs BIGINT, real_installs BIGINT, free INTEGER, price TEXT, currency TEXT,
    contains_ads INTEGER, ad_supported INTEGER, offers_iap INTEGER, iap_price TEXT,
    content_rating TEXT, released TEXT, updated TEXT, version TEXT, android_version TEXT,
    summary TEXT, description TEXT, recent_changes TEXT, icon TEXT, header_image TEXT,
    screenshots_json TEXT, video TEXT, url TEXT, indie_score INTEGER, growth_score INTEGER,
    opportunity_score INTEGER, perfil_detectado TEXT, is_giant INTEGER, estimated_mau BIGINT,
    revenue_monthly_usd_low DOUBLE PRECISION, revenue_monthly_usd_base DOUBLE PRECISION, revenue_monthly_usd_high DOUBLE PRECISION,
    profit_monthly_usd_base DOUBLE PRECISION, revenue_monthly_brl_base DOUBLE PRECISION, profit_monthly_brl_base DOUBLE PRECISION,
    financial_confidence TEXT, financial_notes TEXT, review_count_collected BIGINT,
    review_score_avg_recent DOUBLE PRECISION, review_positive_pct DOUBLE PRECISION, review_negative_pct DOUBLE PRECISION,
    review_keywords_json TEXT, review_samples_json TEXT, external_sources_used TEXT,
    external_title TEXT, external_description TEXT, external_markdown_preview TEXT,
    raw_json TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS logs (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT, level TEXT, message TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS api_tests (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL, ok INTEGER NOT NULL DEFAULT 0, status TEXT,
    message TEXT, latency_ms INTEGER, created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apps_run ON apps(run_id);
CREATE INDEX IF NOT EXISTS idx_apps_app_id ON apps(app_id);
CREATE INDEX IF NOT EXISTS idx_apps_profile ON apps(perfil_detectado);
CREATE INDEX IF NOT EXISTS idx_apps_scores ON apps(indie_score, growth_score, opportunity_score);
CREATE INDEX IF NOT EXISTS idx_apps_created ON apps(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_api_tests_provider ON api_tests(provider, created_at);

ALTER TABLE runs ADD COLUMN IF NOT EXISTS control_note TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS parent_run_id BIGINT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS updated_at TEXT;
