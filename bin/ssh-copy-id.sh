#!/usr/bin/env bash

set -eo pipefail
export LC_ALL=C
unset CDPATH

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

PUBLIC_KEY=~/.ssh/id_rsa.pub

error() {
    echo >&2 "* Error: $*"
}

fatal() {
    error "$@"
    exit 1
}

message() {
    echo >&2 "$*"
}

usage() {
    echo "Copy the public SSH key to enable authentication"
    echo
    echo "$0 [options] hostname"
    echo "options:"
    echo "  -f, --public-key-file=          Path to public key file"
    echo "                                  (default: ${PUBLIC_KEY})"
    echo "           --help                 Display this help and exit"
}

RUN_SSH=$THIS_DIR/run-ssh.sh

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--public-key-file)
            PUBLIC_KEY="$2"
            shift 2
            ;;
        --public-key-file=*)
            PUBLIC_KEY="${1#*=}"
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

if [[ -z "$1" ]]; then
    message "Required hostname"
    exit
fi

message "Copy public key file: $PUBLIC_KEY"

set -xe
"$RUN_SSH" "$@" "{ mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod go-rwx ~ && chmod go-rwx ~/.ssh && chmod go-rwx ~/.ssh/authorized_keys; }" < "$PUBLIC_KEY"
