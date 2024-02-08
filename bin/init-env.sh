# shellcheck shell=bash
BIN_DIR=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

PROJ_DIR=$BIN_DIR/..

: "${CFG_INIT_ENV_CONFIG:=$PROJ_DIR/init-env.cfg}"

# Load init-env.cfg configuration
if [[ -n "$CFG_INIT_ENV_CONFIG" && -e "$CFG_INIT_ENV_CONFIG" ]]; then
    # shellcheck disable=SC1090
    . "$CFG_INIT_ENV_CONFIG"
fi

: "${CFG_CONFIG_FILE:=$PROJ_DIR/config.yml}"

# shellcheck disable=SC2034
CFG_CONFIG_FILE_DIR=$(dirname -- "$CFG_CONFIG_FILE")

: "${CFG_DEBUG_CONFIG:=true}"

: "${CFG_SHELL_CONFIG_ENABLED:=true}"

: "${CFG_VENV_ENABLED:=true}"

message() {
    echo >&2 "* $*"
}

error() {
    echo >&2 "Error: $*"
}

fatal() {
    error "$@"
    exit 1
}

is-true() {
    case "$1" in
        true | yes | 1) return 0 ;;
    esac
    return 1
}

is-array() {
    declare -p "$1" &>/dev/null && [[ "$(declare -p "$1")" =~ "declare -a" ]]
}

# https://www.linuxjournal.com/content/normalizing-path-names-bash

normpath() {
    # Remove all /./ sequences.
    local path=${1//\/.\//\/}

    # Remove dir/.. sequences.
    while [[ $path =~ ([^/][^/]*/\.\./) ]]; do
        path=${path/${BASH_REMATCH[0]}/}
    done
    echo "$path"
}

if test -x /usr/bin/realpath; then
    abspath() {
        if [[ -d "$1" || -d "$(dirname "$1")" ]]; then
            /usr/bin/realpath "$1"
        else
            case "$1" in
                "" | ".") echo "$PWD";;
                /*) normpath "$1";;
                *)  normpath "$PWD/$1";;
            esac
        fi
    }
else
    abspath() {
        if [[ -d "$1" ]]; then
            (cd "$1" || exit 1; pwd)
        else
            case "$1" in
                "" | ".") echo "$PWD";;
                /*) normpath "$1";;
                *)  normpath "$PWD/$1";;
            esac
        fi
    }
fi

activate-venv() { :; }
deactivate-venv() { :; }

init-venv() {
    local venv_activate_path
    if is-true "$CFG_VENV_ENABLED"; then
        if [[ -d "${CFG_VENV_DIR:-}" && -e "${CFG_VENV_DIR:-}/bin/activate" ]]; then
            venv_activate_path=$CFG_VENV_DIR/bin/activate
        else
            local venv_dir
            for venv_dir in "$PROJ_DIR"/.venv "$PROJ_DIR"/venv "$PROJ_DIR"/*-venv "$PROJ_DIR"/*-env; do
                if [[ -d "$venv_dir" && -e "$venv_dir/bin/activate" ]]; then
                    venv_activate_path=$venv_dir/bin/activate
                fi
            done
        fi
        if [[ -n "$venv_activate_path" ]]; then
            eval "
                activate-venv() {
                    if [[ -z \"\$NO_ECHO\" ]]; then
                        message \"Activated venv ${venv_activate_path}\"
                    fi
                    . \"${venv_activate_path}\";
                };
                deactivate-venv() { deactivate; };
            "
        fi
    fi
}

PY=
PY_VERSION=

init-python-3() {
    local i py py_version
    unset PY PY_VERSION
    # Detect python excutable
    for i in python3 python; do
        if command -v "$i" &>/dev/null; then
            py=$(command -v "$i")
            py_version=$("$py" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
            case "$py_version" in
                3.*)
                    PY=$py
                    # shellcheck disable=SC2034
                    PY_VERSION=$py_version
                    break;;
            esac
        fi
    done
    if [[ -n "$PY" ]]; then
        if [[ -z "$NO_ECHO" ]]; then
            message "Use python: $PY"
        fi
        return 0
    else
        error "No Python 3.x found"
        return 1
    fi
}

# http://stackoverflow.com/questions/1203583/how-do-i-rename-a-bash-function
# http://unix.stackexchange.com/questions/29689/how-do-i-redefine-a-bash-function-in-terms-of-old-definition
copy-fn() {
    local fn;
    fn="$(declare -f "$1")" && eval "function $(printf %q "$2") ${fn#*"()"}";
}

rename-fn() {
    copy-fn "$@" && unset -f "$1";
}

_ALL_CB=()

declare-callback() {
    if [[ -z "${1:-}" ]]; then
        echo >&2 "No callback name specified"
        return 1
    fi
    local cb_name=$1 cb_var_name sh_code i
    for i in "${_ALL_CB[@]}"; do
        if [[ "$i" == "$cb_name" ]]; then
            # callback was already registered
            return 0
        fi
    done
    _ALL_CB+=("$cb_name")
    cb_var_name=${cb_name^^}
    cb_var_name=_CB_${cb_var_name//[.-]/_}
    printf -v sh_code "
    %s=() # List of function names to be executed
    run-%s-callback() {
        local cb_name
        for cb_name in \"\${%s[@]}\"; do
            \"\$cb_name\" \"\$@\"
        done
    }
    " "$cb_var_name" "$cb_name" "$cb_var_name"
    eval "$sh_code"
}

register-callback() {
    if [[ -z "${1:-}" ]]; then
        echo >&2 "No callback name specified"
        return 1
    fi
    local cb_name=$1 cb_var_name sh_code num_cb new_cb_name
    cb_var_name=${cb_name^^}
    cb_var_name=_CB_${cb_var_name//[.-]/_}
    if declare -F "$cb_name" > /dev/null; then
        # Each config file can define callback with the same name,
        # rename callback function to avoid collisions
        eval "num_cb=\${#${cb_var_name}[@]}"
        new_cb_name=$cb_name-$num_cb
        rename-fn "$cb_name" "$new_cb_name"
        eval "${cb_var_name}+=(\"$new_cb_name\")"
    fi
}

register-all-callbacks() {
    local cb_name
    for cb_name in "${_ALL_CB[@]}"; do
        register-callback "$cb_name"
    done
}

declare-callback pre-ansible

# load-script loads script with correctly defined THIS_DIR environment variable
load-script() {
    local script_file=$1 THIS_DIR
    # shellcheck disable=SC2034
    THIS_DIR=$(cd "$(dirname -- "${script_file}")" && pwd -P)
    # shellcheck disable=SC1090
    . "$script_file"

    register-all-callbacks
}

load-scripts() {
    local script
    for script in "${@}"; do
        if [[ -e "$script" ]]; then
            load-script "$script"
        else
            error "Script file '$script' not found !"
        fi
    done
}

init-ansible() {
    local bin_path old_path
    if command -v ansible &>/dev/null; then
        return 0
    fi
    old_path=$PATH
    for bin_path in "$HOME/bin" "$HOME/.local/bin"; do
        if [ -d "$bin_path" ] ; then
            PATH="$bin_path:$old_path"
        fi
        if command -v ansible &>/dev/null; then
            return 0
        fi
    done
    echo >&2 "Could not find ansible executable"
    return 1
}

# Detect venv
init-venv

# Activate venv
activate-venv

# Detect python excutable
init-python-3

# Detect ansible
init-ansible

# If used variables are not set in init-env.cfg script, initialize them
if ! is-array CFG_ANSIBLE_INVENTORIES; then
    CFG_ANSIBLE_INVENTORIES=( )
fi

if ! is-array CFG_ANSIBLE_EXTRA_VARS; then
    CFG_ANSIBLE_EXTRA_VARS=()
fi

if ! is-array CFG_ANSIBLE_VAULT_FILES; then
    CFG_ANSIBLE_VAULT_FILES=()
fi

if ! is-array CFG_ANSIBLE_VARS_FILES; then
    CFG_ANSIBLE_VARS_FILES=()
fi

if ! is-array CFG_CONFIGURE_OPTS; then
    CFG_CONFIGURE_OPTS=()
fi

abspath() {
    readlink -f "${1}" 2>/dev/null || \
        "$PY" -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "${1}"
}

join-by() {
  local IFS="$1"
  shift
  echo "$*"
}

check-config() {
    if [[ -n "${ANSIBLE_PRIVATE_KEY_FILE}" ]]; then
        if [[ ! -e "${ANSIBLE_PRIVATE_KEY_FILE}" || ! -e "${ANSIBLE_PRIVATE_KEY_FILE}.pub" ]]; then
            fatal "SSH keys ${ANSIBLE_PRIVATE_KEY_FILE} or ${ANSIBLE_PRIVATE_KEY_FILE}.pub missing, run $(abspath "$THIS_DIR/configure.sh")"
        fi
    fi
}

add-inventories-to-opts() {
    # opts array is defined outside
    local inventory
    for inventory in "${CFG_ANSIBLE_INVENTORIES[@]}"; do
      opts+=( -i "$inventory" )
    done
}

add-vault-config-to-opts() {
    local vault_password_file vault_id
    for vault_password_file in "${CFG_ANSIBLE_VAULT_PASSWORD_FILES[@]}"; do
        opts+=( "--vault-password-file=$vault_password_file" )
    done
    for vault_id in "${CFG_ANSIBLE_VAULT_IDS[@]}"; do
      opts+=( "--vault-id=$vault_id" )
    done
}

add-remote-user-to-opts() {
    # opts array is defined outside
    if [[ -n "$ANSIBLE_REMOTE_USER" ]]; then
        opts+=(--user "$ANSIBLE_REMOTE_USER")
    fi
}

add-extra-vars-to-opts() {
    local fn var
    # opts array is defined outside
    opts+=(
        --extra-vars "project_root_dir=$PROJ_DIR"
        --extra-vars "project_ansible_config_file=$CFG_ANSIBLE_CONFIG_FILE"
    )
    for var in "${CFG_ANSIBLE_EXTRA_VARS[@]}"; do
        if [[ -n "$var" ]]; then
            opts+=(--extra-vars "$var")
        fi
    done
    for fn in "${CFG_ANSIBLE_VARS_FILES[@]}"; do
        if [[ -e "$fn" ]]; then
            opts+=(--extra-vars @"$fn")
        fi
    done
    for fn in "${CFG_ANSIBLE_VAULT_FILES[@]}"; do
        if [[ -e "$fn" ]]; then
            opts+=(--extra-vars @"$fn")
        fi
    done
}

run-ansible-cmd() {
    # opts array is defined outside
    local cmd=$1
    shift

    run-pre-ansible-callback

    if [[ -z "$NO_ECHO" ]]; then
        echo >&2 "+ ${cmd} \
${opts[*]} \
$*"
    fi
    "${cmd}" \
        "${opts[@]}" \
        "$@"
}

run-ansible() {
    local opts
    opts=()
    add-inventories-to-opts
    add-vault-config-to-opts
    add-remote-user-to-opts
    add-extra-vars-to-opts

    run-ansible-cmd ansible "$@"
}

run-ansible-inventory() {
    local opts
    opts=()
    add-inventories-to-opts
    add-vault-config-to-opts
    # remote user and extra vars are not supported by ansible-inventory

    run-ansible-cmd ansible-inventory "$@"
}

run-ansible-vault() {
    local opts
    opts=()

    if [[ "$1" != -* ]]; then
        opts+=("$1")
        shift
    fi

    # inventories, remote users and extra vars are not supported by ansible-vault
    add-vault-config-to-opts

    run-ansible-cmd ansible-vault "$@"
}

run-ansible-playbook() {
    check-config

    local opts
    opts=()
    add-inventories-to-opts
    add-vault-config-to-opts
    add-remote-user-to-opts
    add-extra-vars-to-opts

    run-ansible-cmd ansible-playbook "$@"
}

run-ansible-galaxy() {
    local opts
    opts=()

    run-ansible-cmd ansible-galaxy "$@"
}

run-ansible-config() {
    local opts
    opts=()

    run-ansible-cmd ansible-config "$@"
}

run-ansible-doc() {
    local opts
    opts=()

    run-ansible-cmd ansible-doc "$@"
}

run-ansible-console() {
    local opts
    opts=()
    add-inventories-to-opts
    add-vault-config-to-opts
    add-remote-user-to-opts

    run-ansible-cmd ansible-console "$@"
}

run-ansible-lint() {
    check-config

    local opts
    opts=()
    add-inventories-to-opts
    add-remote-user-to-opts

    run-ansible-cmd ansible-lint "$@"
}

# $1 - filename
# $2 - variable prefix, CFG_ is used by default
read-config-file() {
    local configfile=$1
    local prefix=$2
    if [[ ! -f "$configfile" ]]; then echo >&2 "[read-config-file] '$configfile' is not a file"; return 1; fi
    if [[ -z "$prefix" ]]; then prefix=CFG_; fi

    local lhs rhs cfg exitcode

    cfg=$(tr -d '\r' < "$configfile")
    exitcode=$?
    if [ "$exitcode" != "0" ]; then return $exitcode; fi

    while IFS='=' read -rs lhs rhs;
    do
        if [[ "$lhs" =~ ^[A-Za-z_][A-Za-z_0-9]*$ && -n "$lhs" ]]; then
            rhs="${rhs%%\#*}"               # Del in line right comments
            rhs="${rhs%"${rhs##*[^ ]}"}"    # Del trailing spaces
            rhs="${rhs%\"*}"                # Del opening string quotes
            rhs="${rhs#\"*}"                # Del closing string quotes
            declare -g "${prefix}${lhs}=${rhs}"
        fi
    done <<<"$cfg"
}

run-configure() {
    "$PY" "$BIN_DIR/configure.py" "${CFG_CONFIGURE_OPTS[@]}" "$@"
}

if is-true "$CFG_SHELL_CONFIG_ENABLED"; then
    if is-true "$CFG_DEBUG_CONFIG"; then
        CFG_SHELL_CONFIG=$(run-configure --shell-config)
    else
        CFG_SHELL_CONFIG=$(run-configure --shell-config 2>/dev/null)
    fi

    eval "$CFG_SHELL_CONFIG"

    if is-array CFG_ANSIBLE_USER_SCRIPTS; then
        load-scripts "${CFG_ANSIBLE_USER_SCRIPTS[@]}"
    fi
fi

for var_name in ANSIBLE_PRIVATE_KEY_FILE ANSIBLE_VAULT_ENCRYPT_IDENTITY ANSIBLE_LOG_PATH; do
    cfg_var_name="CFG_${var_name}"
    if [[ -n "${!cfg_var_name}" ]]; then
        printf -v cmd "export $var_name=%q" "${!cfg_var_name}"
        if [[ -z "$NO_ECHO" ]]; then
            echo >&2 "+ $cmd"
        fi
        eval "$cmd"
    fi
done
if [[ -n "$CFG_ANSIBLE_CONFIG_FILE" ]]; then
    export ANSIBLE_CONFIG=$CFG_ANSIBLE_CONFIG_FILE
fi

if is-array CFG_VAULT_FILES; then
    CFG_ANSIBLE_VAULT_FILES+=( "${CFG_VAULT_FILES[@]}" )
fi

if is-array CFG_VARS_FILES; then
    CFG_ANSIBLE_VARS_FILES+=( "${CFG_VARS_FILES[@]}" )
fi

unset var_name cfg_var_name
