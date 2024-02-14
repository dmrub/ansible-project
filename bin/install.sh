#!/usr/bin/env bash

set -eo pipefail
export LC_ALL=C.UTF-8
unset CDPATH

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

usage() {
    echo "Install dependencies and configure Ansible project"
    echo
    echo "$0 [options]"
    echo "options:"
    echo "  -p, --proj-dir proj_dir      Project directory"
    echo "  -e, --venv-dir venv_dir      Virtual environment directory"
    echo "      --install-dependencies   Install only system-wide dependencies"
    echo "      --dont-install-dependencies"
    echo "                               Install everything, but no system-wide dependencies"
    echo "      --force                  Force installation of already installed components"
    echo "      --                       End of options"
}

NO_DEPENDENCIES=
ONLY_DEPENDENCIES=
INSTALL_ANSIBLE_OPTS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
    -e | --venv-dir)
        INSTALL_ANSIBLE_OPTS+=("$1" "$2")
        shift 2
        ;;
    -p | --proj-dir)
        INSTALL_ANSIBLE_OPTS+=("$1" "$2")
        shift 2
        ;;
    --install-dependencies)
        ONLY_DEPENDENCIES=true
        INSTALL_ANSIBLE_OPTS+=("$1")
        shift
        ;;
    --dont-install-dependencies)
        NO_DEPENDENCIES=true
        INSTALL_ANSIBLE_OPTS+=("$1")
        shift
        ;;
    --force)
        INSTALL_ANSIBLE_OPTS+=("$1")
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

if [[ "$NO_DEPENDENCIES" = "true" && "$ONLY_DEPENDENCIES" = "true" ]]; then
    fatal "You cannot specify the --install-dependencies and --dont-install-dependencies options at the same time"
fi

if [[ "$ONLY_DEPENDENCIES" = "true" ]]; then
    "$THIS_DIR"/install-ansible.sh "${INSTALL_ANSIBLE_OPTS[@]}"
else
    "$THIS_DIR"/install-ansible.sh "${INSTALL_ANSIBLE_OPTS[@]}"
    "$THIS_DIR"/configure.sh
    "$THIS_DIR"/update.sh

    # User-defined post installation
    if [[ -x "$THIS_DIR/user-install.sh" ]]; then
        "$THIS_DIR/user-install.sh"
    fi
    if [[ -x "$THIS_DIR/../scripts/user-install.sh" ]]; then
        "$THIS_DIR/../scripts/user-install.sh"
    fi
fi
