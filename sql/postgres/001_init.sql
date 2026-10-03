-- The application owns tables prefixed with flowguard_.
-- n8n owns its own tables in the same local-development database.
-- SQLAlchemy creates the portable schema at API startup.
CREATE SCHEMA IF NOT EXISTS flowguard;

