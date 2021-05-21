#!/usr/bin/env bash

THIS_DIR=$( (cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) )

set -eo pipefail

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

run-ansible-vault "$@"
