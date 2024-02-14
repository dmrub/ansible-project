#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

LOCAL_PORT=58079

RUN_SSH=$THIS_DIR/run-ssh.sh

error() {
    echo >&2 "Error: $*"
}

fatal() {
    error "$@"
    exit 1
}

usage() {
    echo "Run browser with connection via SOCKS tunnel to the remote host"
    echo
    echo "$0 [options] [--] remote-host [url]"
    echo "options:"
    echo "      -b, --browser BROWSER_PATH"
    echo "                             Use specified browser executable"
    echo "      -l, --remote-localhost 127.0.0.1 and localhost should refer to the remote host"
    echo "      --help                 Display this help and exit"
    echo "      --                     End of options"
    echo ""
    echo "This tool will try to find a compatible browser. If no browser is detected,"
    echo "the browser specified in the command line will be checked first and then"
    echo "the browser defined in the environment variable BROWSER."
}

_get_children_pids() {
    local pid=$1
    local all_pids=$2
    local children
    while IFS= read -r child; do
        children="$(_get_children_pids "$child" "$all_pids") $child $children"
    done < <(awk "{ if ( \$2 == $pid ) { print \$1 } }" <<<"$all_pids")
    echo "$children"
}

get_children_pids() {
    local pid=$1 all_pids
    all_pids=$(ps -o pid,ppid -ax)
    _get_children_pids "$pid" "$all_pids"
}

REMOTE_LOCALHOST=false

while [[ "$1" == "-"* ]]; do
    case "$1" in
        -b|--browser)
            BROWSER="$2"
            shift 2
            ;;
        --browser=*)
            BROWSER="${1#*=}"
            shift
            ;;
        -l|--remote-localhost)
            REMOTE_LOCALHOST=true
            shift
            ;;
        --help)
            usage
            exit
            ;;
        --)
            shift
            break
            ;;
        -*)
            fatal "Unknown option $1"
            ;;
        *)
            break
            ;;
    esac
done

if [[ $# -eq 0 ]]; then
    fatal "Remote host missing"
fi

REMOTE_HOST=$1
shift

BROWSER_PID=
TMPDIR=$(mktemp -d /tmp/browser-socks.XXXXXXXXXX)
cleanup() {
    if [[ -n "$BROWSER_PID" ]]; then
        echo "Kill browser PID $BROWSER_PID"
        kill "$BROWSER_PID" > /dev/null 2>&1 || true;
    fi
    if [[ -n "$SSH_PID" ]]; then
        echo "Kill ssh PID $SSH_PID"
        # shellcheck disable=SC2046
        kill $(get_children_pids "$SSH_PID") "$SSH_PID" > /dev/null 2>&1 || true;
        # kill "$SSH_PID" > /dev/null 2>&1 || true;
    fi
    echo "Delete $TMPDIR"
    rm -rf "$TMPDIR"
}

trap cleanup INT TERM EXIT

BROWSER_EXEC=
TMP_EXEC=
for BROWSER_NAME in "${BROWSER}" chromium-browser firefox google-chrome; do
    TMP_EXEC=$(type -p "$BROWSER_NAME" || true)
    if [[ -x "$TMP_EXEC" ]]; then
        BROWSER_EXEC=$TMP_EXEC
        break
    fi
    echo >&2 "Could not find '$BROWSER_NAME' executable !"
done

if [[ ! -x "$BROWSER_EXEC" ]]; then
    fatal "Could not detect any supported browser executable !"
fi

BROWSER_BN=$(basename -- "$BROWSER_EXEC")

case "$BROWSER_BN" in
    firefox)
        BROWSER_TYPE=firefox
        ;;
    google-chrome|chromium-browser)
        BROWSER_TYPE=chromium
        ;;
    *)
        fatal "Unsupported browser $BROWSER_BN"
        ;;
esac

case "$BROWSER_TYPE" in
    chromium)
        if [[ "$REMOTE_LOCALHOST" = "true" ]]; then
            ARGS=(--proxy-bypass-list="<-loopback>")
        else
            ARGS=()
        fi
        set -x
        "$BROWSER_EXEC" \
            --user-data-dir="$TMPDIR" \
            --proxy-server="socks5://127.0.0.1:${LOCAL_PORT}" \
            --host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE 127.0.0.1" \
            "${ARGS[@]}" \
            "$@" &
        BROWSER_PID=$!
        set +x
        ;;
    firefox)
        cat > "$TMPDIR/user.js" <<EOF
// Mozilla User Preferences

user_pref("app.normandy.first_run", false);
user_pref("network.predictor.cleaned-up", true);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", ${LOCAL_PORT});
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.allow_hijacking_localhost", ${REMOTE_LOCALHOST});
user_pref("network.proxy.type", 1);
EOF
        set -x
        "$BROWSER_EXEC" --profile "$TMPDIR" "$@" &
        BROWSER_PID=$!
        set +x
        ;;
    *)
        fatal "Unsupported browser type $BROWSER_TYPE, should be one of: chromium, firefox"
        ;;
esac

set -x
"$RUN_SSH" -N -D "$LOCAL_PORT" "$REMOTE_HOST" &
SSH_PID=$!
wait -f "$BROWSER_PID"
set +x
