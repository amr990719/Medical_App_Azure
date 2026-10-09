#!/usr/bin/env bash
# PostgreSQL Flexible Server: Entra administrator, application database and the managed
# identity's role (PROMPT.md §26, docs/azure-deployment.md). Idempotent.
#
#   1. Sets the Entra administrator (default: the signed-in user; prefer a group for prod).
#   2. Connects as that administrator with an Entra access token (no password anywhere).
#   3. Creates the application database (owned by the Entra administrator) if missing.
#   4. Creates the role of the app's user-assigned identity with
#      pgaadauth_create_principal_with_oid (non-admin, bound to the identity's object id).
#   5. Grants it CONNECT/CREATE/TEMPORARY on the database and USAGE/CREATE on schema public:
#      the migrate job (same identity) creates and therefore owns the tables.
#
# Requires: az, psql (PostgreSQL client >= 15). The server must be reachable from this machine:
# with public access use --allow-current-ip (a temporary firewall rule, removed on exit); with
# private networking run the script from inside the VNet.
#
# Usage:
#   infrastructure/scripts/setup-postgres-entra.sh \
#     --resource-group <rg> --server <postgres-server-name> --identity-name <id-medsyn-dev> \
#     [--database medical] \
#     [--admin-object-id <id> --admin-name <display-name-or-upn> --admin-type Group|User|ServicePrincipal] \
#     [--allow-current-ip]
set -euo pipefail

usage() {
    sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

resource_group=""
server=""
identity_name=""
database="medical"
admin_object_id=""
admin_name=""
admin_type="User"
allow_current_ip=false

while [ $# -gt 0 ]; do
    case "$1" in
        --resource-group) resource_group="${2:?}"; shift 2 ;;
        --server) server="${2:?}"; shift 2 ;;
        --identity-name) identity_name="${2:?}"; shift 2 ;;
        --database) database="${2:?}"; shift 2 ;;
        --admin-object-id) admin_object_id="${2:?}"; shift 2 ;;
        --admin-name) admin_name="${2:?}"; shift 2 ;;
        --admin-type) admin_type="${2:?}"; shift 2 ;;
        --allow-current-ip) allow_current_ip=true; shift ;;
        -h | --help) usage 0 ;;
        *) echo "Unknown argument: $1" >&2; usage 2 ;;
    esac
done

if [ -z "$resource_group" ] || [ -z "$server" ] || [ -z "$identity_name" ]; then
    echo "--resource-group, --server and --identity-name are required" >&2
    exit 2
fi
case "$admin_type" in
    Group | User | ServicePrincipal) ;;
    *) echo "--admin-type must be Group, User or ServicePrincipal" >&2; exit 2 ;;
esac
command -v az >/dev/null || { echo "Azure CLI (az) is required" >&2; exit 1; }
command -v psql >/dev/null || { echo "psql (PostgreSQL client) is required" >&2; exit 1; }

if [ -z "$admin_object_id" ]; then
    admin_object_id="$(az ad signed-in-user show --query id -o tsv)"
    admin_name="$(az ad signed-in-user show --query userPrincipalName -o tsv)"
    admin_type="User"
fi
[ -n "$admin_name" ] || { echo "--admin-name is required with --admin-object-id" >&2; exit 2; }

identity_object_id="$(az identity show -g "$resource_group" -n "$identity_name" --query principalId -o tsv)"
host="$(az postgres flexible-server show -g "$resource_group" -n "$server" \
    --query fullyQualifiedDomainName -o tsv)"

# 1. Entra administrator.
existing_admin="$(az postgres flexible-server microsoft-entra-admin list \
    -g "$resource_group" -s "$server" --query "[?objectId=='${admin_object_id}'] | length(@)" -o tsv)"
if [ "$existing_admin" = "0" ]; then
    echo "Setting Entra administrator ${admin_name} on ${server}"
    az postgres flexible-server microsoft-entra-admin create \
        -g "$resource_group" -s "$server" \
        --object-id "$admin_object_id" --display-name "$admin_name" --type "$admin_type" \
        --output none
else
    echo "Entra administrator ${admin_name} already set"
fi

rule_name=""
cleanup() {
    if [ -n "$rule_name" ]; then
        echo "Removing temporary firewall rule ${rule_name}"
        az postgres flexible-server firewall-rule delete -g "$resource_group" --server-name "$server" \
            --name "$rule_name" --yes --output none || true
    fi
}
trap cleanup EXIT

if [ "$allow_current_ip" = true ]; then
    my_ip="$(curl -fsS https://api.ipify.org)"
    rule_name="setup-$(date -u +%Y%m%d%H%M%S)"
    echo "Adding temporary firewall rule ${rule_name} for this machine"
    az postgres flexible-server firewall-rule create -g "$resource_group" --server-name "$server" \
        --name "$rule_name" --start-ip-address "$my_ip" --end-ip-address "$my_ip" --output none
fi

# 2. Entra access token as the password (valid ~1 hour; never printed).
PGPASSWORD="$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)"
export PGPASSWORD
export PGSSLMODE=require

run_psql() {
    psql "host=${host} port=5432 user=${admin_name} dbname=$1" \
        --no-psqlrc --set ON_ERROR_STOP=1 --quiet \
        --set db="$database" --set ident="$identity_name" --set oid="$identity_object_id"
}

# 3 + 4. Database and identity role (server level, connected to the `postgres` database).
run_psql postgres <<'SQL'
SELECT format('CREATE DATABASE %I', :'db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec

SELECT 'SELECT * FROM pgaadauth_create_principal_with_oid('
       || quote_literal(:'ident') || ', ' || quote_literal(:'oid') || ', ''service'', false, false)'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'ident') \gexec
SQL

# 5. Least privilege inside the application database.
run_psql "$database" <<'SQL'
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE :"db" TO :"ident";
GRANT USAGE, CREATE ON SCHEMA public TO :"ident";
SQL

cat <<EOF

PostgreSQL is ready for the ${identity_name} identity:
  DATABASE_URL=postgres://${identity_name}@${host}:5432/${database}
  DB_AUTH_MODE=entra
  DB_SSLMODE=require
(main.bicep sets these on the Container App and its jobs.)
EOF
