"""Turn on TLS in the LOCAL docker compose PostgreSQL (self-signed certificate).

Production settings refuse database connections without TLS (`DB_SSLMODE` must be require /
verify-ca / verify-full, PROMPT.md §26), so running the production image locally against the
compose database needs a server that speaks TLS. The alpine image ships no `openssl`, so the
certificate is generated here with `cryptography` and copied into the data directory through
`docker exec`; `ALTER SYSTEM SET ssl = on` + reload enables it (persisted in the volume).
Clients using `sslmode=prefer` (development settings) keep working.

Local development only — the key never leaves the throwaway compose volume. Usage:
    python backend/scripts/local_postgres_tls.py [--container medical-syndicates-postgres-1]
Undo: `ALTER SYSTEM RESET ssl; SELECT pg_reload_conf();` (or `docker compose down -v`).
"""

import argparse
import datetime
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def self_signed(hostnames: list[str]) -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0])])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(h) for h in hostnames]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


def docker_exec(container: str, command: str, stdin: bytes | None = None) -> str:
    result = subprocess.run(  # noqa: S603 — fixed argv, local docker only
        ["docker", "exec", "-i", "-u", "postgres", container, "sh", "-c", command],  # noqa: S607
        input=stdin,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode().strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--container", default="medical-syndicates-postgres-1")
    parser.add_argument("--user", default="medical")
    parser.add_argument("--database", default="medical")
    args = parser.parse_args()

    cert, key = self_signed(["postgres", "localhost"])
    data = docker_exec(args.container, 'echo "$PGDATA"')
    docker_exec(args.container, f"umask 077 && cat > {data}/server.key", stdin=key)
    docker_exec(args.container, f"cat > {data}/server.crt", stdin=cert)
    psql = f"psql -U {args.user} -d {args.database} -tAc"
    docker_exec(args.container, f'{psql} "ALTER SYSTEM SET ssl = on"')
    docker_exec(args.container, f'{psql} "SELECT pg_reload_conf()"')
    print("ssl =", docker_exec(args.container, f'{psql} "SHOW ssl"'))


if __name__ == "__main__":
    main()
