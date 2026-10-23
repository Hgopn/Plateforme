#!/bin/sh
set -eu

# Runs only on a new PostgreSQL volume. The API role owns its database but is
# not a PostgreSQL superuser. Psql reads the password from its environment;
# neither the command line nor stdout contains it.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password INTERARCADE_DB_PASSWORD
SELECT format('CREATE ROLE interarcade LOGIN PASSWORD %L', :'app_password') \gexec
ALTER DATABASE interarcade OWNER TO interarcade;
ALTER SCHEMA public OWNER TO interarcade;
SQL
