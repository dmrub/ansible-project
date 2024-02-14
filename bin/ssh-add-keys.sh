#!/usr/bin/env bash

set -eo pipefail

PROG=$(basename "$0")
SSH_ENV_FILE="$HOME/.ssh/agent-env"

error() {
    echo >&2 "Error: $*"
}

message() {
    echo >&2 "$*"
}

fatal() {
    error "$@"
    exit 1
}

usage() {
    local prog_spaces
    prog_spaces=$(tr '[:print:]' ' ' <<<"$PROG")
    echo "$PROG - adds the SSH private key to the identities of the OpenSSH authentication agent"
    echo "${prog_spaces}   if the key has not yet been added"
    echo
    echo "This script starts ssh-agent if it is not running."
    echo "You need to run this script in combination with 'eval'"
    echo "to add the configuration of ssh-agent to the current shell environment, e.g."
    echo
    echo "eval \$($PROG ~/.ssh/id_ed25519)"
    echo
    echo "$0 [options] [ssh-private-key ...]"
    echo "options:"
    echo "      -a, --ssh-agent        Start ssh-agent and exit"
    echo "      --help                 Display this help and exit"
    echo "      --                     End of options"
}

is-ssh-agent-pid-valid() {
    if [ -z "$1" ]; then
        return 1
    fi
    # shellcheck disable=SC2009
    ps -o pid,comm -ax | grep "$1" | grep -v grep | grep ssh-agent > /dev/null;
}

start-ssh-agent() {
    local print_env _SSH_AGENT_PID _SSH_AUTH_SOCK
    _SSH_AGENT_PID=${SSH_AGENT_PID:-}
    _SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-}
    if [[ -z "$SSH_AGENT_PID" || -z "$SSH_AUTH_SOCK" ]]; then
        print_env=true
    fi
    if [ -f "$SSH_ENV_FILE" ]; then
        # shellcheck disable=SC1090
        . "$SSH_ENV_FILE" > /dev/null
        if [[ "$SSH_AGENT_PID" != "$_SSH_AGENT_PID" || "$SSH_AUTH_SOCK" != "$_SSH_AUTH_SOCK" ]]; then
            print_env=true
        fi
    fi
    if ! is-ssh-agent-pid-valid "$SSH_AGENT_PID" || ! ssh-add -l > /dev/null 2>&1; then
        local _old_umask
        _old_umask=$(umask)
        umask 0077
        mkdir -p "$(dirname "$SSH_ENV_FILE")"
        ssh-agent -s > "$SSH_ENV_FILE"
        umask "$_old_umask"
        # shellcheck disable=SC1090
        . "$SSH_ENV_FILE" > /dev/null
        message "Started ssh-agent with PID $SSH_AGENT_PID"
        print_env=true
    fi
    if [ -n "$print_env" ]; then
        cat "$SSH_ENV_FILE"
    fi
}

add-ssh-keys() {
    start-ssh-agent
    if [[ "$#" -eq 0 ]]; then
        ssh-add
    else
        local key_fp key
        for key in "$@"; do
            key_fp=$(ssh-keygen -lf "$key" | awk '{ print $2 }')
            if ! ssh-add -l | grep -q "$key_fp"; then
                ssh-add "$key"
            fi
        done
    fi
}

OPT_SSH_AGENT=

while [[ "$1" == "-"* ]]; do
    case "$1" in
        -a|--ssh-agent)
            OPT_SSH_AGENT=true
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

if [[ -n "$OPT_SSH_AGENT" ]]; then
    start-ssh-agent
    exit
fi

add-ssh-keys "$@"
