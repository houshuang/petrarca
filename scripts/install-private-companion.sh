#!/bin/bash
# Install the private Companion backend environment and nginx capability route.
set -euo pipefail
umask 077

CAPABILITY_FILE="${1:-/etc/petrarca-companion-capability}"
COMPANION_ENV_FILE="${2:-/etc/petrarca-companion.env}"
SERVICE="petrarca-research.service"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN="${DROPIN_DIR}/20-companion-env.conf"
TLS_SITE="${PETRARCA_TLS_SITE:-/etc/nginx/sites-available/petrarca-expo-ssl}"
SNIPPET="/etc/nginx/snippets/petrarca-companion.conf"
TEMPLATE="$(cd "$(dirname "$0")" && pwd)/nginx-petrarca-companion.conf.template"
INCLUDE_LINE='    include /etc/nginx/snippets/petrarca-companion.conf;'

if (( EUID != 0 )); then
  echo "Private Companion installation must run as root" >&2
  exit 1
fi

require_private_root_file() {
  local path="$1"
  local label="$2"
  local metadata

  if [[ ! -f "$path" || -L "$path" ]]; then
    echo "$label must be a regular, non-symlink file" >&2
    exit 1
  fi
  metadata="$(stat -c '%u:%g:%a' -- "$path")"
  if [[ "$metadata" != '0:0:600' ]]; then
    echo "$label must be owned by root:root with mode 0600" >&2
    exit 1
  fi
}

require_private_root_file "$CAPABILITY_FILE" "Capability file"
require_private_root_file "$COMPANION_ENV_FILE" "Companion environment file"

if [[ ! -f "$TEMPLATE" || -L "$TEMPLATE" ]]; then
  echo "Companion nginx template is missing or unsafe" >&2
  exit 1
fi
if [[ ! -f "$TLS_SITE" || -L "$TLS_SITE" ]]; then
  echo "TLS nginx site must be a regular, non-symlink file" >&2
  exit 1
fi
if [[ -L "$SNIPPET" ]]; then
  echo "Refusing to replace a symlinked Companion nginx snippet" >&2
  exit 1
fi
if [[ -e "$DROPIN" && ( ! -f "$DROPIN" || -L "$DROPIN" ) ]]; then
  echo "Refusing to replace an unsafe Companion systemd drop-in" >&2
  exit 1
fi
if [[ -e "$DROPIN_DIR" && ( ! -d "$DROPIN_DIR" || -L "$DROPIN_DIR" ) ]]; then
  echo "Companion systemd drop-in directory is unsafe" >&2
  exit 1
fi

# Validate both secret files without placing either value in argv, stdout, or
# the process environment. Restricting the EnvironmentFile path to a direct
# child of /etc keeps the generated systemd directive unambiguous.
python3 - "$CAPABILITY_FILE" "$COMPANION_ENV_FILE" <<'PY'
import re
import sys
from pathlib import Path

capability_path = Path(sys.argv[1])
environment_path = Path(sys.argv[2])

capability = capability_path.read_text(encoding="utf-8")
if not re.fullmatch(r"petrarca-private-[0-9a-f]{64}\n?", capability):
    raise SystemExit("Capability file must contain exactly one valid private path")

if (
    environment_path.parent != Path("/etc")
    or not re.fullmatch(r"[A-Za-z0-9_.-]+", environment_path.name)
):
    raise SystemExit("Companion environment file must live directly under /etc")

required = {"SONIOX_API_KEY": [], "PETRARCA_RESURFACING_KEY": []}
unexpected = []
malformed = False
for raw_line in environment_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        malformed = True
        continue
    name, value = line.split("=", 1)
    name = name.strip()
    if name not in required:
        unexpected.append(name)
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    required[name].append(value)

invalid = [
    name for name, assignments in required.items()
    if len(assignments) != 1 or not assignments[0]
]
if invalid:
    raise SystemExit(
        "Companion environment must contain exactly one nonempty assignment for: "
        + ", ".join(sorted(invalid))
    )
if len(required["PETRARCA_RESURFACING_KEY"][0].encode("utf-8")) < 32:
    raise SystemExit("PETRARCA_RESURFACING_KEY must contain at least 32 bytes")
if unexpected or malformed:
    raise SystemExit("Companion environment must contain only its two required assignments")
PY

ROLLBACK_DIR="$(mktemp -d /etc/.petrarca-companion.rollback.XXXXXX)"
TMP_DROPIN=''
TMP_SNIPPET=''
TMP_TLS_SITE=''
DROPIN_DIR_EXISTED=0
DROPIN_EXISTED=0
SNIPPET_EXISTED=0
SERVICE_WAS_ACTIVE=0
SERVICE_CHANGED=0
NGINX_CHANGED=0
TRANSACTION_ACTIVE=0
KEEP_ROLLBACK=0

pretransaction_cleanup() {
  local status=$?
  trap - EXIT
  [[ -z "${TMP_DROPIN:-}" ]] || rm -f -- "$TMP_DROPIN"
  [[ -z "${TMP_SNIPPET:-}" ]] || rm -f -- "$TMP_SNIPPET"
  [[ -z "${TMP_TLS_SITE:-}" ]] || rm -f -- "$TMP_TLS_SITE"
  case "$ROLLBACK_DIR" in
    /etc/.petrarca-companion.rollback.*) rm -rf -- "$ROLLBACK_DIR" ;;
    *) echo "Refusing to remove unexpected rollback path" >&2 ;;
  esac
  if (( ! DROPIN_DIR_EXISTED )); then
    rmdir -- "$DROPIN_DIR" 2>/dev/null || true
  fi
  exit "$status"
}
trap pretransaction_cleanup EXIT

if [[ -d "$DROPIN_DIR" ]]; then
  DROPIN_DIR_EXISTED=1
else
  mkdir -p -- "$DROPIN_DIR"
  chown root:root "$DROPIN_DIR"
  chmod 755 "$DROPIN_DIR"
fi
TMP_DROPIN="$(mktemp "${DROPIN_DIR}/.petrarca-companion.XXXXXX")"
TMP_SNIPPET="$(mktemp /etc/nginx/snippets/.petrarca-companion.XXXXXX)"
TMP_TLS_SITE="$(mktemp "$(dirname "$TLS_SITE")/.petrarca-companion-site.XXXXXX")"

if systemctl is-active --quiet "$SERVICE"; then
  SERVICE_WAS_ACTIVE=1
fi
if ! systemctl cat "$SERVICE" >"$ROLLBACK_DIR/systemd-unit.log" 2>&1; then
  echo "Petrarca research service is not installed" >&2
  exit 1
fi

cp -a -- "$TLS_SITE" "$ROLLBACK_DIR/tls-site"
if [[ -e "$DROPIN" ]]; then
  cp -a -- "$DROPIN" "$ROLLBACK_DIR/dropin"
  DROPIN_EXISTED=1
fi
if [[ -e "$SNIPPET" ]]; then
  if [[ ! -f "$SNIPPET" ]]; then
    echo "Existing Companion nginx snippet is not a regular file" >&2
    exit 1
  fi
  cp -a -- "$SNIPPET" "$ROLLBACK_DIR/snippet"
  SNIPPET_EXISTED=1
fi

# Stage a minimal drop-in. The validated EnvironmentFile remains root-only;
# neither secret is copied into the unit or systemctl's command line.
python3 - "$TMP_DROPIN" "$COMPANION_ENV_FILE" <<'PY'
import sys
from pathlib import Path

output = Path(sys.argv[1])
environment_path = Path(sys.argv[2])
output.write_text(
    "[Service]\n"
    f"EnvironmentFile={environment_path}\n"
    "Environment=RESEARCH_HOST=127.0.0.1\n"
    "UMask=0077\n",
    encoding="utf-8",
)
PY
chown root:root "$TMP_DROPIN"
chmod 644 "$TMP_DROPIN"

# Render the capability-bearing snippet without exposing the capability in a
# command argument. The temporary lives beside its destination for atomic mv.
python3 - "$TEMPLATE" "$CAPABILITY_FILE" "$TMP_SNIPPET" <<'PY'
import re
import sys
from pathlib import Path

template_path = Path(sys.argv[1])
capability_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

template = template_path.read_text(encoding="utf-8")
if "__CAPABILITY_PATH__" not in template:
    raise SystemExit("Companion nginx template has no capability placeholder")
capability = capability_path.read_text(encoding="utf-8").rstrip("\n")
if not re.fullmatch(r"petrarca-private-[0-9a-f]{64}", capability):
    raise SystemExit("Capability became invalid during installation")
output_path.write_text(
    template.replace("__CAPABILITY_PATH__", capability),
    encoding="utf-8",
)
PY
chown root:root "$TMP_SNIPPET"
chmod 600 "$TMP_SNIPPET"

# Stage the TLS site update separately. There is currently one server block;
# inserting before its final brace preserves all unrelated locations verbatim.
python3 - "$TLS_SITE" "$TMP_TLS_SITE" "$INCLUDE_LINE" <<'PY'
import sys
from pathlib import Path

source = Path(sys.argv[1])
output = Path(sys.argv[2])
include = sys.argv[3]
text = source.read_text(encoding="utf-8")
if include not in text.splitlines():
    closing = text.rfind("\n}")
    if closing < 0:
        raise SystemExit("Could not locate the TLS server block closing brace")
    text = text[:closing] + "\n" + include + text[closing:]
output.write_text(text, encoding="utf-8")
PY
chown --reference="$TLS_SITE" "$TMP_TLS_SITE"
chmod --reference="$TLS_SITE" "$TMP_TLS_SITE"

restore_file_atomically() {
  local backup="$1"
  local destination="$2"
  local temporary

  temporary="$(mktemp "$(dirname "$destination")/.petrarca-companion-restore.XXXXXX")" || return 1
  if ! cp -a -- "$backup" "$temporary" \
      || ! mv -f -- "$temporary" "$destination"; then
    rm -f -- "$temporary"
    return 1
  fi
}

restore_prior_nginx() {
  local failed=0
  set +e
  restore_file_atomically "$ROLLBACK_DIR/tls-site" "$TLS_SITE" || failed=1
  if (( SNIPPET_EXISTED )); then
    restore_file_atomically "$ROLLBACK_DIR/snippet" "$SNIPPET" || failed=1
  else
    rm -f -- "$SNIPPET" || failed=1
  fi
  if (( ! failed )) \
      && nginx -t >"$ROLLBACK_DIR/rollback-nginx-test.log" 2>&1 \
      && systemctl reload nginx >"$ROLLBACK_DIR/rollback-nginx-reload.log" 2>&1; then
    set -e
    return 0
  fi
  set -e
  return 1
}

restore_prior_service() {
  local failed=0
  set +e
  if (( DROPIN_EXISTED )); then
    restore_file_atomically "$ROLLBACK_DIR/dropin" "$DROPIN" || failed=1
  else
    rm -f -- "$DROPIN" || failed=1
  fi
  systemctl daemon-reload >"$ROLLBACK_DIR/rollback-daemon-reload.log" 2>&1 || failed=1
  if (( SERVICE_WAS_ACTIVE )); then
    systemctl restart "$SERVICE" >"$ROLLBACK_DIR/rollback-service-restart.log" 2>&1 \
      || failed=1
    systemctl is-active --quiet "$SERVICE" || failed=1
  else
    systemctl stop "$SERVICE" >"$ROLLBACK_DIR/rollback-service-stop.log" 2>&1 \
      || failed=1
  fi
  if (( ! DROPIN_DIR_EXISTED )); then
    rmdir -- "$DROPIN_DIR" 2>/dev/null || true
  fi
  set -e
  (( ! failed ))
}

rollback_transaction() {
  local failed=0
  if (( NGINX_CHANGED )); then
    restore_prior_nginx || failed=1
  fi
  if (( SERVICE_CHANGED )); then
    restore_prior_service || failed=1
  fi
  if (( failed )); then
    KEEP_ROLLBACK=1
    echo "URGENT: Companion installation rollback needs manual repair" >&2
    return 1
  fi
  echo "Companion installation failed; prior service and nginx state restored" >&2
}

cleanup() {
  local status=$?
  local rollback_status=0
  trap - EXIT

  if (( status != 0 && TRANSACTION_ACTIVE )); then
    rollback_transaction || rollback_status=1
  fi
  [[ -z "${TMP_DROPIN:-}" ]] || rm -f -- "$TMP_DROPIN"
  [[ -z "${TMP_SNIPPET:-}" ]] || rm -f -- "$TMP_SNIPPET"
  [[ -z "${TMP_TLS_SITE:-}" ]] || rm -f -- "$TMP_TLS_SITE"
  if (( ! KEEP_ROLLBACK )); then
    case "$ROLLBACK_DIR" in
      /etc/.petrarca-companion.rollback.*) rm -rf -- "$ROLLBACK_DIR" ;;
      *) echo "Refusing to remove unexpected rollback path" >&2 ;;
    esac
  fi
  if (( status == 0 && rollback_status != 0 )); then
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT

verify_companion_service() {
  local main_pid
  systemctl is-active --quiet "$SERVICE" || return 1
  main_pid="$(systemctl show --property MainPID --value "$SERVICE")" || return 1
  [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || return 1

  # Inspect names/non-emptiness only. Never print or compare secret values.
  python3 - "$main_pid" <<'PY'
import sys
from pathlib import Path

payload = Path(f"/proc/{sys.argv[1]}/environ").read_bytes()
environment = {}
for entry in payload.split(b"\0"):
    if b"=" not in entry:
        continue
    name, value = entry.split(b"=", 1)
    environment[name] = value
required = (b"SONIOX_API_KEY", b"PETRARCA_RESURFACING_KEY")
if any(not environment.get(name) for name in required):
    raise SystemExit("Companion service is missing a required environment key")
if environment.get(b"RESEARCH_HOST") != b"127.0.0.1":
    raise SystemExit("Companion service is not loopback-bound")
PY

  curl --fail --silent --max-time 1 --output /dev/null \
    http://127.0.0.1:8090/companion
}

# Commit and verify the backend half of the transaction first. No public route
# exists until the restarted process has both required keys and answers locally.
TRANSACTION_ACTIVE=1
if ! mv -f -- "$TMP_DROPIN" "$DROPIN"; then
  echo "Could not install the Companion systemd drop-in" >&2
  exit 1
fi
TMP_DROPIN=''
SERVICE_CHANGED=1
if ! systemctl daemon-reload >"$ROLLBACK_DIR/daemon-reload.log" 2>&1; then
  echo "Systemd daemon reload failed" >&2
  exit 1
fi
if ! systemctl restart "$SERVICE" >"$ROLLBACK_DIR/service-restart.log" 2>&1; then
  echo "Petrarca research service restart failed" >&2
  exit 1
fi

SERVICE_VERIFIED=0
for _ in {1..60}; do
  if verify_companion_service >"$ROLLBACK_DIR/service-verify.log" 2>&1; then
    SERVICE_VERIFIED=1
    break
  fi
  sleep 0.5
done
if (( ! SERVICE_VERIFIED )); then
  echo "Petrarca research service did not pass private Companion verification" >&2
  exit 1
fi

if ! mv -f -- "$TMP_SNIPPET" "$SNIPPET"; then
  echo "Could not install the Companion nginx snippet" >&2
  exit 1
fi
TMP_SNIPPET=''
NGINX_CHANGED=1
if ! mv -f -- "$TMP_TLS_SITE" "$TLS_SITE"; then
  echo "Could not install the Companion TLS-site include" >&2
  exit 1
fi
TMP_TLS_SITE=''

# Diagnostics remain root-only because nginx errors can include the capability
# URI. Nothing from these logs is echoed to the terminal.
if ! nginx -t >"$ROLLBACK_DIR/nginx-test.log" 2>&1; then
  echo "Nginx rejected the Companion route" >&2
  exit 1
fi
if ! verify_companion_service >"$ROLLBACK_DIR/service-pre-exposure.log" 2>&1; then
  echo "Petrarca research service stopped before nginx exposure" >&2
  exit 1
fi
if ! systemctl reload nginx >"$ROLLBACK_DIR/nginx-reload.log" 2>&1; then
  echo "Nginx reload failed" >&2
  exit 1
fi

TRANSACTION_ACTIVE=0
echo "Private Petrarca Companion backend and route installed (secrets redacted)."
