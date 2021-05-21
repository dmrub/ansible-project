#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

set -x
git -C "$PROJ_DIR" submodule update --init --recursive
set +x
if [[ -e "$PROJ_DIR/manifest.yml" ]]; then
    set -x
    run-ansible-playbook "$PROJ_DIR/playbooks/manifest-install.yml"
    set +x
fi
