#!/usr/bin/env sh
set -eu

infra_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
template="$infra_dir/.env.example"
output="$infra_dir/.env"

if [ -e "$output" ] && [ "${1:-}" != "--force" ]; then
  echo "infra/.env already exists. Back it up, or rerun with --force to replace it." >&2
  exit 1
fi
command -v openssl >/dev/null 2>&1 || { echo "openssl is required." >&2; exit 1; }

random_urlsafe() {
  openssl rand -base64 "$1" | tr '+/' '-_' | tr -d '=\n'
}

cp "$template" "$output"
replace() {
  key=$1
  value=$2
  escaped=$(printf '%s' "$value" | sed 's/[&|]/\\&/g')
  sed -i.bak "s|^${key}=.*|${key}=${escaped}|" "$output"
}
replace APP_ENV production
replace DJANGO_SECRET_KEY "$(random_urlsafe 64)"
replace DJANGO_DEBUG false
replace FIELD_ENCRYPTION_KEY "$(random_urlsafe 32)="
replace DB_PASSWORD "$(random_urlsafe 32)"
replace MINIO_ROOT_PASSWORD "$(random_urlsafe 32)"
replace INTERNAL_API_TOKEN "$(random_urlsafe 48)"
rm -f "$output.bak"
chmod 600 "$output"
echo "Created infra/.env with generated production secrets."
echo "Set the host/origin variables to your domain before deployment."
