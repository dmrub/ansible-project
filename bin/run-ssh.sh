#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

RUN_SSH=$THIS_DIR/_run-ssh.sh
SSH_CONFIG=$THIS_DIR/_ssh-config

if [[ ! -e "$RUN_SSH" || ! -e "$SSH_CONFIG" ]]; then
    "$THIS_DIR"/create-ssh-scripts.sh
fi

"$RUN_SSH" "$@"
