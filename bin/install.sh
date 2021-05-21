#!/usr/bin/env bash

set -eo pipefail
export LC_ALL=C
unset CDPATH

THIS_DIR=$( (cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P))

if [[ "$1" = "--help" ]]; then
    echo "Install all dependencies and configure Ansible project"
    echo
    echo "$0 [options]"
    echo "options:"
    echo "           --help                 Display this help and exit"
    exit
fi

"$THIS_DIR"/install-ansible.sh
"$THIS_DIR"/configure.sh
"$THIS_DIR"/update.sh
