#!/bin/sh
set -e

THIS_DIR=$(cd "$(dirname -- "$0")" && pwd -P)

# Ansible installation script
# Based on https://github.com/docker/docker-install/blob/master/install.sh
# Apache License 2.0
# This script is meant for quick & easy install via:
#   $ curl -fsSL URI/ansible-install.sh -o ansible-install.sh
#   $ sh ansible-install.sh

error() {
    echo >&2 "Error: $*"
}

fatal() {
    error "$@"
    exit 1
}

message() {
    echo >&2 "* $*"
}

command_exists() {
    command -v "$@" >/dev/null 2>&1
}

is_dry_run() {
    if [ -z "$DRY_RUN" ]; then
        return 1
    else
        return 0
    fi
}

is_wsl() {
    case "$(uname -r)" in
    *microsoft*) true ;; # WSL 2
    *Microsoft*) true ;; # WSL 1
    *) false ;;
    esac
}

is_darwin() {
    case "$(uname -s)" in
    *darwin*) true ;;
    *Darwin*) true ;;
    *) false ;;
    esac
}

get_distribution() {
    lsb_dist=""
    # Every system that we officially support has /etc/os-release
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        lsb_dist="$(. /etc/os-release && echo "$ID")"
    fi
    # Returning an empty string here should be alright since the
    # case statements don't act unless you provide an actual value
    echo "$lsb_dist"
}

add_debian_backport_repo() {
    debian_version="$1"
    backports="deb http://ftp.debian.org/debian $debian_version-backports main"
    if ! grep -Fxq "$backports" /etc/apt/sources.list; then
        (
            set -x
            $sh_c "echo \"$backports\" >> /etc/apt/sources.list"
        )
    fi
}

# Check if this is a forked Linux distro
check_forked() {

    # Check for lsb_release command existence, it usually exists in forked distros
    if command_exists lsb_release; then
        # Check if the `-u` option is supported
        set +e
        lsb_release -a -u >/dev/null 2>&1
        lsb_release_exit_code=$?
        set -e

        # Check if the command has exited successfully, it means we're in a forked distro
        if [ "$lsb_release_exit_code" = "0" ]; then
            # Print info about current distro
            cat <<-EOF
			You're using '$lsb_dist' version '$dist_version'.
			EOF

            # Get the upstream release info
            lsb_dist=$(lsb_release -a -u 2>&1 | tr '[:upper:]' '[:lower:]' | grep -E 'id' | cut -d ':' -f 2 | tr -d '[:space:]')
            dist_version=$(lsb_release -a -u 2>&1 | tr '[:upper:]' '[:lower:]' | grep -E 'codename' | cut -d ':' -f 2 | tr -d '[:space:]')

            # Print info about upstream distro
            cat <<-EOF
			Upstream release is '$lsb_dist' version '$dist_version'.
			EOF
        else
            if [ -r /etc/debian_version ] && [ "$lsb_dist" != "ubuntu" ] && [ "$lsb_dist" != "raspbian" ]; then
                if [ "$lsb_dist" = "osmc" ]; then
                    # OSMC runs Raspbian
                    lsb_dist=raspbian
                else
                    # We're Debian and don't even know it!
                    lsb_dist=debian
                fi
                dist_version="$(sed 's/\/.*//' /etc/debian_version | sed 's/\..*//')"
                case "$dist_version" in
                10)
                    dist_version="buster"
                    ;;
                9)
                    dist_version="stretch"
                    ;;
                8 | 'Kali Linux 2')
                    dist_version="jessie"
                    ;;
                esac
            fi
        fi
    fi
}

install_dependencies() {
    message "The root user is required to install the system-wide dependencies"
    message "Run this script with the --dont-install-dependencies option"
    message "if you have already installed the dependencies or want to install them manually"

    user="$(id -un 2>/dev/null || true)"

    sh_c='sh -c'
    if [ "$user" != 'root' ]; then
        if command_exists sudo; then
            sh_c='sudo -E sh -c'
        elif command_exists su; then
            sh_c='su -c'
        else
            cat >&2 <<-'EOF'
			Error: this installer needs the ability to run commands as root.
			We are unable to find either "sudo" or "su" available to make this happen.
			EOF
            exit 1
        fi
    fi

    if is_dry_run; then
        sh_c="echo"
    fi

    message "Installing dependencies"

    # perform some very rudimentary platform detection
    lsb_dist=$(get_distribution)
    lsb_dist="$(echo "$lsb_dist" | tr '[:upper:]' '[:lower:]')"

    case "$lsb_dist" in
    ubuntu)
        if command_exists lsb_release; then
            dist_version="$(lsb_release --codename | cut -f2)"
        fi
        if [ -z "$dist_version" ] && [ -r /etc/lsb-release ]; then
            # shellcheck disable=SC1091
            dist_version="$(. /etc/lsb-release && echo "$DISTRIB_CODENAME")"
        fi
        ;;

    debian | raspbian)
        dist_version="$(sed 's/\/.*//' /etc/debian_version | sed 's/\..*//')"
        case "$dist_version" in
        10)
            dist_version="buster"
            ;;
        9)
            dist_version="stretch"
            ;;
        8)
            dist_version="jessie"
            ;;
        esac
        ;;

    centos | rhel)
        if [ -z "$dist_version" ] && [ -r /etc/os-release ]; then
            # shellcheck disable=SC1091
            dist_version="$(. /etc/os-release && echo "$VERSION_ID")"
        fi
        ;;

    *)
        if command_exists lsb_release; then
            dist_version="$(lsb_release --release | cut -f2)"
        fi
        if [ -z "$dist_version" ] && [ -r /etc/os-release ]; then
            # shellcheck disable=SC1091
            dist_version="$(. /etc/os-release && echo "$VERSION_ID")"
        fi
        ;;
    esac

    # Check if this is a forked Linux distro
    check_forked

    # Run setup for each distro accordingly
    case "$lsb_dist" in
    ubuntu)

        (
            if ! is_dry_run; then
                set -x
            fi
            $sh_c 'apt-get update -qq >/dev/null'
            $sh_c 'apt-get install -y --no-install-recommends python3-minimal python3-pip python3-venv git openssh-client gnupg pinentry-tty sshpass'
        )
        ;;
    debian | raspbian)
        (
            if ! is_dry_run; then
                set -x
            fi
            $sh_c 'apt-get update -qq >/dev/null'
            $sh_c 'apt-get install -y --no-install-recommends python3 python3-pip python3-venv git openssh-client gnupg pinentry-tty sshpass'
        )
        ;;
    centos | fedora | rhel)
        set +e
        (
            if ! is_dry_run; then
                set -x
            fi
            $sh_c 'yum check-update'
        )
        EC=$?
        set -e
        if [ $EC -ne 0 ] && [ $EC -ne 100 ]; then
            fatal "yum check-update failed with exit code $EC"
        fi
        (
            if ! is_dry_run; then
                set -x
            fi
            $sh_c 'yum install -y python3 libselinux-python3 python3-pip git gnupg2 pinentry which sshpass'
        )
        ;;
    *)
        if is_darwin; then
            if ! command_exists brew; then
                if is_dry_run; then
                    # shellcheck disable=SC2016
                    echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"'
                else
                (
                    set -x
                    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
                )
                fi
            fi
            if ! command_exists brew; then
                fatal "Could not install brew"
            fi
            if is_dry_run; then
                echo brew install bash
                echo hash -r
            else
                (
                    set -x
                    brew install bash
                    hash -r
                )
            fi
            if ! command_exists sshpass; then
                if is_dry_run; then
                    echo 'curl -o sshpass-1.08.tar.gz -L  https://sourceforge.net/projects/sshpass/files/sshpass/1.08/sshpass-1.08.tar.gz'
                    echo 'tar xvzf sshpass-1.08.tar.gz'
                    echo 'cd sshpass-1.08'
                    echo './configure'
                    echo 'sudo make install'
                    echo 'rm -rf sshpass-1.08'
                else
                    (
                        set -x
                        curl -o sshpass-1.08.tar.gz -L  https://sourceforge.net/projects/sshpass/files/sshpass/1.08/sshpass-1.08.tar.gz && \
                            tar xvzf sshpass-1.08.tar.gz
                        cd sshpass-1.08
                        ./configure
                        sudo make install
                        rm -rf sshpass-1.08
                    )
                fi
            fi
        else
            fatal "Unsupported distribution '$lsb_dist'"
        fi
        ;;
    esac
}

usage() {
    echo "Install Ansible"
    echo
    echo "$0 [options]"
    echo "options:"
    echo "  -p, --proj-dir proj_dir      Project directory"
    echo "  -e, --venv-dir venv_dir      Virtual environment directory"
    echo "  -n, --dry-run                Don't actually install anything, just print commands"
    echo "      --install-dependencies   Install only system-wide dependencies"
    echo "      --dont-install-dependencies"
    echo "                               Install everything, but no system-wide dependencies"
    echo "      --force                  Force installation of already installed components"
    echo "      --                       End of options"
}

DRY_RUN=
VENV_DIR=
NO_DEPENDENCIES=
ONLY_DEPENDENCIES=
FORCE=
PROJ_DIR=

while [ $# -gt 0 ]; do
    case "$1" in
    -n | --dry-run)
        DRY_RUN=true
        shift
        ;;
    -e | --venv-dir)
        VENV_DIR="$2"
        shift 2
        ;;
    -p | --proj-dir)
        PROJ_DIR="$2"
        shift 2
        ;;
    --install-dependencies)
        ONLY_DEPENDENCIES=true
        shift
        ;;
    --dont-install-dependencies)
        NO_DEPENDENCIES=true
        shift
        ;;
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

if [ "$NO_DEPENDENCIES" = "true" ] && [ "$ONLY_DEPENDENCIES" = "true" ]; then
    fatal "You cannot specify the --install-dependencies and --dont-install-dependencies options at the same time"
fi

if [ "$ONLY_DEPENDENCIES" = "true" ]; then
    message "Installing only system-wide dependencies"
    install_dependencies
else
    if [ "$NO_DEPENDENCIES" != "true" ]; then
        install_dependencies
    else
        message "User disabled installation of dependencies"
    fi

    if [ -z "$PROJ_DIR" ]; then
        for p in "$THIS_DIR" "$THIS_DIR/.."; do
            if [ -e "$p/requirements.txt" ]; then
                PROJ_DIR=$p
                break
            fi
        done
    fi

    if [ -z "$PROJ_DIR" ]; then
        fatal "The project directory was not specified and also not found automatically"
    fi

    if [ ! -e "$PROJ_DIR/requirements.txt" ]; then
        fatal "No requirements.txt file found in the project directory: $PROJ_DIR"
    fi

    if [ -z "$VENV_DIR" ]; then
        VENV_DIR=$PROJ_DIR/venv
    fi

    message "Project directory: $PROJ_DIR"
    message "Virtual environment directory: $VENV_DIR"

    sh_c='sh -c'
    if is_dry_run; then
        sh_c="echo"
    fi

    # Install virtualenv module
    if ! python3 -m venv --help >/dev/null; then
        (
            if ! is_dry_run; then
                set -x
            fi
            $sh_c 'python3 -m pip install --user virtualenv'
        )
    fi

    # Create virtualenv
    if [ ! -e "$VENV_DIR/bin/activate" ]; then
        VENV_PARENT_DIR=$(dirname -- "$VENV_DIR")
        VENV_BN=$(basename -- "$VENV_DIR")
        if is_dry_run; then
            echo mkdir -p "$VENV_PARENT_DIR"
            echo cd "$VENV_PARENT_DIR"
            echo python3 -m venv "$VENV_BN"
            echo . "$VENV_DIR/bin/activate"
            echo python3 -m pip install --upgrade pip
            echo deactivate
        else
            (
                set -x
                mkdir -p "$VENV_PARENT_DIR"
                cd "$VENV_PARENT_DIR"
                python3 -m venv "$VENV_BN"
            )
            (
                # shellcheck disable=SC1091
                . "$VENV_DIR/bin/activate"
                set -x
                python3 -m pip install --upgrade pip
            )
        fi
    fi

    # Install requirements
    if is_dry_run; then
        echo . "$VENV_DIR/bin/activate"
        echo python3 -m pip install -r "$PROJ_DIR/requirements.txt"
        if is_darwin; then
            echo python3 -m pip install passlib
        fi
        echo deactivate
    else
        (
            # shellcheck disable=SC1091
            . "$VENV_DIR/bin/activate"
            set -x
            python3 -m pip install -r "$PROJ_DIR/requirements.txt"
            set +x
            if is_darwin; then
                set -x
                python3 -m pip install passlib
                set +x
            fi
        )
    fi

    # Install ansible requirements
    if [ -e "$PROJ_DIR/requirements.yml" ]; then
        if [ "$FORCE" = "true" ]; then
            FORCE_INSTALL_ARG="--force"
        else
            FORCE_INSTALL_ARG=""
        fi
        if is_dry_run; then
            echo . "$VENV_DIR/bin/activate"
            echo "ansible-galaxy collection install ${FORCE_INSTALL_ARG} -r \"$PROJ_DIR/requirements.yml\""
        else
            (
                # shellcheck disable=SC1091
                . "$VENV_DIR/bin/activate"
                set -x
                # shellcheck disable=SC2086
                ansible-galaxy collection install ${FORCE_INSTALL_ARG} -r "$PROJ_DIR/requirements.yml"
                # shellcheck disable=SC2086
                ansible-galaxy role install ${FORCE_INSTALL_ARG} -r "$PROJ_DIR/requirements.yml"
            )
        fi
    fi

    message "Finished installation of requirements"
fi
