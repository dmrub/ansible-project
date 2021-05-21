#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

RUN_RSYNC=$THIS_DIR/_run-rsync.sh
SSH_CONFIG=$THIS_DIR/_ssh-config

if [[ ! -e "$RUN_RSYNC" || ! -e "$SSH_CONFIG" ]]; then
    "$THIS_DIR"/create-ssh-scripts.sh
fi

"$RUN_RSYNC" "$@"
