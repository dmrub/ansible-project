#!/usr/bin/env bash

THIS_DIR=$( (cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) )

set -eo pipefail

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

usage() {
    echo "Run shell commands"
    echo
    echo "$0 [options] [-- [ansible-options]] shell-command"
    echo "options:"
    echo "  -p, --host-pattern=        Ansible host pattern"
    echo "                             (default: $PATTERN)"
    echo "  -b, --become               run operations with become"
    echo "  -v,-vv,-vvv,-vvvv          run in verbose mode"
    echo "      --verbose"
    echo "      --help                 Display this help and exit"
    echo "      --                     End of options"
}

HOST_PATTERN=all
BECOME=
ANSIBLE_OPTS=()

while [[ "$1" == "-"* ]]; do
    case "$1" in
        -p|--host-pattern)
            HOST_PATTERN="$2"
            shift 2
            ;;
        --host-pattern=*)
            HOST_PATTERN="${1#*=}"
            shift
            ;;
        -b|--become)
            BECOME=--become
            shift
            ;;
        -v|-vv|-vvv|-vvvv|--verbose)
            ANSIBLE_OPTS+=("$1")
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

run-ansible "$HOST_PATTERN" $BECOME "${ANSIBLE_OPTS[@]}" -m shell --args "$@"
