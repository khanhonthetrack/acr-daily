-- The app's Steam sign-in comes back to the app itself on its own PC (RFC 8252 loopback) instead of being polled for:
-- the port it listens on at 127.0.0.1, the sha256 of a secret only it knows (its verifier), and the sha256 of the
-- one-time code the browser takes back to it. Anyone who had the state could pick the token up from /auth/poll; that
-- is gone (apps from 0.0.20 sign in this way, signed-in older apps keep their token). Needs 0024 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0025_app_signin.sql
ALTER TABLE logins ADD COLUMN port INTEGER;
ALTER TABLE logins ADD COLUMN challenge TEXT;
ALTER TABLE logins ADD COLUMN code TEXT;
