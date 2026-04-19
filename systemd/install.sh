#!/usr/bin/env bash
# Install the ulanzi-linux systemd user unit.
#
# Usage:
#   ./systemd/install.sh              # install + enable + start
#   ./systemd/install.sh --dry-run    # print what would run
#   ./systemd/install.sh --uninstall  # stop, disable, remove the unit
#
# Idempotent: re-running only reloads the unit on change.

set -euo pipefail

UNIT_NAME="ulanzi-linux.service"
SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC_UNIT="${SRC_DIR}/${UNIT_NAME}"
DST_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
DST_UNIT="${DST_DIR}/${UNIT_NAME}"
DECK_YAML="${HOME}/.config/ulanzi/deck.yaml"
DEFAULT_ULANZI_BIN="${HOME}/.local/bin/ulanzi-linux"
ULANZI_BIN=""
TMP_UNIT=""

# --- helpers ---------------------------------------------------------------

DRY_RUN=0
UNINSTALL=0

log()  { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

# Array-form runner: each argument is kept intact so paths containing
# spaces (e.g. "/home/me/StreamDeck on Linux/...") don't word-split.
# ``eval`` was tempting but mishandles quoted whitespace silently.
run() {
    if (( DRY_RUN )); then
        # Quote each arg so the preview matches what would actually run.
        printf '  +'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

# Some operations (uninstall) tolerate failure; ``run_ok`` drops the
# non-zero exit instead of tripping ``set -e``.
run_ok() {
    if (( DRY_RUN )); then
        printf '  +'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@" || true
    fi
}

cleanup() {
    if [[ -n "${TMP_UNIT}" && -f "${TMP_UNIT}" ]]; then
        rm -f "${TMP_UNIT}"
    fi
}

trap cleanup EXIT

resolve_ulanzi_bin() {
    local candidate=""
    if command -v ulanzi-linux >/dev/null 2>&1; then
        candidate="$(command -v ulanzi-linux)"
        if [[ "${candidate}" == "${HOME}/.pyenv/shims/"* ]] && command -v pyenv >/dev/null 2>&1; then
            local pyenv_candidate=""
            pyenv_candidate="$(pyenv which ulanzi-linux 2>/dev/null || true)"
            if [[ -n "${pyenv_candidate}" && -x "${pyenv_candidate}" ]]; then
                candidate="${pyenv_candidate}"
            fi
        fi
        if [[ -x "${candidate}" ]]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    fi
    if [[ -x "${DEFAULT_ULANZI_BIN}" ]]; then
        printf '%s\n' "${DEFAULT_ULANZI_BIN}"
        return 0
    fi
    return 1
}

build_unit_with_binary() {
    local bin_path="$1"
    TMP_UNIT="$(mktemp)"
    sed "s|^ExecStart=.*$|ExecStart=${bin_path} --json-logs daemon %h/.config/ulanzi/deck.yaml|" \
        "${SRC_UNIT}" > "${TMP_UNIT}"
    printf '%s\n' "${TMP_UNIT}"
}

# --- args ------------------------------------------------------------------

for arg in "$@"; do
    case "$arg" in
        --dry-run)   DRY_RUN=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help)
            sed -n '3,10p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            err "unknown option: $arg"
            exit 2
            ;;
    esac
done

# --- sanity checks ---------------------------------------------------------

if ! command -v systemctl >/dev/null 2>&1; then
    err "systemctl not found — this system does not use systemd."
    exit 1
fi

# --- uninstall path --------------------------------------------------------

if (( UNINSTALL )); then
    log "uninstalling ${UNIT_NAME}"
    # ``disable --now`` fails if the unit was never enabled — tolerate it.
    run_ok systemctl --user disable --now "${UNIT_NAME}"
    run rm -f "${DST_UNIT}"
    run systemctl --user daemon-reload
    log "done."
    exit 0
fi

# --- install path ----------------------------------------------------------

if [[ ! -f "${SRC_UNIT}" ]]; then
    err "unit file not found at ${SRC_UNIT}"
    exit 1
fi

ULANZI_BIN="$(resolve_ulanzi_bin || true)"

if [[ -z "${ULANZI_BIN}" ]]; then
    warn "entry point not found in the active shell or at ${DEFAULT_ULANZI_BIN}"
    warn "install first, then re-run this script from the same Python environment"
else
    log "resolved ulanzi-linux -> ${ULANZI_BIN}"
fi

if [[ ! -f "${DECK_YAML}" ]]; then
    warn "no config at ${DECK_YAML}"
    warn "copy an example:  mkdir -p ~/.config/ulanzi && cp examples/deck.multipage.yaml ${DECK_YAML}"
fi

log "copying ${UNIT_NAME} -> ${DST_UNIT}"
run mkdir -p "${DST_DIR}"
if [[ -n "${ULANZI_BIN}" ]]; then
    TMP_UNIT="$(build_unit_with_binary "${ULANZI_BIN}")"
    run install -m 0644 "${TMP_UNIT}" "${DST_UNIT}"
else
    run install -m 0644 "${SRC_UNIT}" "${DST_UNIT}"
fi

log "reloading user systemd"
run systemctl --user daemon-reload

log "enabling + starting ${UNIT_NAME}"
run systemctl --user enable --now "${UNIT_NAME}"

if (( ! DRY_RUN )); then
    log "status:"
    systemctl --user --no-pager status "${UNIT_NAME}" || true
    log "tail logs with:  journalctl --user -u ${UNIT_NAME} -f"
fi
