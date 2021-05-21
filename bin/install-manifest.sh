#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$( (cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P))

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

usage() {
    echo "Install manifest"
    echo
    echo "$0 [options] [manifest_file]"
    echo "options:"
    echo "      -d,--manifest-install-dir MANIFEST_INSTALL_DIR"
    echo "                               Installation directory, default is project directory:"
    echo "                               $(abspath "$PROJ_DIR")"
    echo "      -v, -vv, -vvv, -vvvv, -vvvvv"
    echo "                               Verbose mode"
    echo "      --help                   Display this help and exit"
    echo "      --                       End of options"
}


MANIFEST_INSTALL_DIR=
OPTS=()

while [[ "$1" == "-"* ]]; do
    case "$1" in
        -d|--manifest-install-dir)
            MANIFEST_INSTALL_DIR=$(abspath "$2")
            shift 2
            ;;
        --manifest-install-dir=*)
            MANIFEST_INSTALL_DIR=$(abspath "${1#*=}")
            shift
            ;;
        -v|-vv|-vvv|-vvvv|-vvvvv)
            OPTS+=("$1")
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

if [[ -n "$MANIFEST_INSTALL_DIR" ]]; then
    OPTS+=(--extra-vars "manifest_install_dir=$MANIFEST_INSTALL_DIR")
fi
if [[ -n "$1" ]]; then
    MANIFEST_FILE=$(abspath "$1")
    OPTS+=(--extra-vars "manifest_file=$MANIFEST_FILE")
    shift
fi

run-ansible-playbook \
    "${OPTS[@]}" \
    "$THIS_DIR/../playbooks/manifest-install.yml" \
    "$@"
