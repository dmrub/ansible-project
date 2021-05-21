#!/usr/bin/env bash

THIS_DIR=$( (cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) )

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

set -e
run-ansible-playbook \
    --extra-vars="dest_dir=$THIS_DIR" \
    --extra-vars="filename_prefix=_" \
    "$THIS_DIR/../playbooks/create-ssh-scripts.yml" \
    "$@"
