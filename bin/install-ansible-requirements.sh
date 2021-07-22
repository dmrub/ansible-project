#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

usage() {
    echo "Install Ansible Requirements"
    echo
    echo "$0 [options]"
    echo "options:"
    echo "      --force                  Force installation of already installed components"
    echo "      --                       End of options"
}

FORCE=

while [[ $# -gt 0 ]]; do
    case "$1" in
    --force)
        FORCE=true
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
        fatal "Illegal option $1"
        ;;
    *)
        break
        ;;
    esac
done

# Install ansible requirements
if [ -e "$PROJ_DIR/requirements.yml" ]; then
    if [ "$FORCE" = "true" ]; then
        FORCE_INSTALL_ARG="--force"
    else
        FORCE_INSTALL_ARG=""
    fi
    # shellcheck disable=SC2086
    run-ansible-galaxy collection install ${FORCE_INSTALL_ARG} -r "$PROJ_DIR/requirements.yml"
    # shellcheck disable=SC2086
    run-ansible-galaxy role install ${FORCE_INSTALL_ARG} -r "$PROJ_DIR/requirements.yml"
fi

message "Finished installation of requirements"
