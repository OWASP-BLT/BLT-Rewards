-- Add is_admin flag to approved_users
-- Apply with: wrangler d1 execute blt-bacon-db --remote --file=migrations/0002_add_is_admin.sql
ALTER TABLE approved_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;
