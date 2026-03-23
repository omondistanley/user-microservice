-- Sprint 2: user correction feedback loop for the transaction classifier.
-- When the user corrects a classification (e.g. "Uber Eats" → Food, not Entertainment)
-- we store the normalised merchant text + their chosen category so the embedding
-- prototype cache can be refined and correction history surfaced in the UI.
-- Run: python run_migration.py migrations/025_classifier_corrections.sql

CREATE SCHEMA IF NOT EXISTS expenses_db;

CREATE TABLE IF NOT EXISTS expenses_db.classifier_correction (
    correction_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        INTEGER      NOT NULL,
    -- The normalised merchant+note text that was misclassified (lowercased, prefix-stripped)
    merchant_text  TEXT         NOT NULL,
    -- What the classifier originally returned
    original_category_code   SMALLINT     NOT NULL,
    original_category_name   VARCHAR(64)  NOT NULL,
    original_source          VARCHAR(32)  NOT NULL DEFAULT 'keyword',  -- keyword|fuzzy|embedding
    original_confidence      NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    -- What the user corrected it to
    corrected_category_code  SMALLINT     NOT NULL,
    corrected_category_name  VARCHAR(64)  NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Fast lookup: for a given user + merchant_text, find the most recent correction
CREATE INDEX IF NOT EXISTS idx_classifier_correction_user_merchant
    ON expenses_db.classifier_correction (user_id, merchant_text, created_at DESC);

-- Aggregate query: most-corrected merchants globally (for model retraining signal)
CREATE INDEX IF NOT EXISTS idx_classifier_correction_merchant_category
    ON expenses_db.classifier_correction (merchant_text, corrected_category_code);

COMMENT ON TABLE expenses_db.classifier_correction IS
    'Gold-label training signal: stores every user correction of the transaction classifier. '
    'Used to (a) override future classifications for the same merchant text per user, '
    'and (b) feed periodic re-embedding of prototype sentences in Sprint 3+.';
