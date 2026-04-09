-- Migration 005: Authentication - rexus_users table
-- Stores user credentials and roles for JWT-based authentication.

CREATE TABLE IF NOT EXISTS rexus_users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50) UNIQUE NOT NULL,
    email       VARCHAR(100),
    password_hash VARCHAR(255) NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'analyst'
                CHECK (role IN ('admin', 'analyst', 'viewer')),
    is_active   BOOLEAN DEFAULT true,
    must_change_password BOOLEAN DEFAULT false,
    created_at  TIMESTAMP DEFAULT NOW(),
    last_login  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rexus_users_username ON rexus_users (username);
CREATE INDEX IF NOT EXISTS idx_rexus_users_role ON rexus_users (role);
