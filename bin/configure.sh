#!/usr/bin/env bash

set -eo pipefail

THIS_DIR=$( cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P )

# BUGFIX: disabled this feature because for some configuration operations
# environment variables defined in the configuration file must be defined.
# Disable the call of configure.py from inside the init-env.sh script
# CFG_SHELL_CONFIG_ENABLED=false

# shellcheck source=init-env.sh
source "$THIS_DIR/init-env.sh"

run-configure "$@"
