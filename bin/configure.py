#!/usr/bin/env python3

"""Ansible configurator"""

import collections.abc
import getpass
import logging
import os.path
import pathlib
import pprint
import random
import readline
import shlex
import string
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Optional, Mapping, List, Dict, Callable

import yaml
from marshmallow import Schema, fields, post_load, post_dump  # type: ignore

try:
    from yaml import CSafeLoader as Loader, CDumper as Dumper  # type: ignore
except ImportError:
    from yaml import SafeLoader as Loader, Dumper  # type: ignore

LOG = logging.getLogger(__name__)

# Default configuration
HOME = os.path.expanduser("~")
THIS_DIR = os.path.dirname(os.path.realpath(__file__))
PROJ_DIR = os.path.join(THIS_DIR, "..")
CONFIG_DIR = os.path.join(HOME, ".ansible")

CONFIG_DEFAULTS = {
    'ansible': {
        'config_file': 'ansible.cfg',
        'inventories': ['inventory']
    }
}

DEFAULT_CONFIG_FILE = os.path.join(PROJ_DIR, "config.yml")


def is_sequence(value):
    return isinstance(value, (list, tuple))


def to_list(value):
    if not value:
        return []
    elif isinstance(value, tuple):
        return list(value)
    elif not isinstance(value, list):
        return [value]
    return value


def to_abspath_list(value):
    return [os.path.abspath(p) for p in to_list(value) if p]


def to_realpath_list(value):
    return [os.path.realpath(p) for p in to_list(value) if p]


def str_or_none(value) -> Optional[str]:
    if value is None:
        return value
    return str(value)


def none_to_empty_str(val):
    return "" if val is None else val


def array_none_to_empty_str(arr):
    return foreach(arr, none_to_empty_str)


def array_join_comma(arr):
    return ",".join(arr)


def to_shell_var_name(s):
    for c in "^°!\"§$%&/()[]{}=?;:,.-<>|'":
        s = s.replace(c, "_")
    return s.upper()


def dict_to_shell_vars(dict_value, var_prefix="", export_vars=False, preprocess_var=None):
    assert isinstance(dict_value, dict)
    result = []
    for key, value in dict_value.items():
        var_name = var_prefix + to_shell_var_name(key)
        if isinstance(value, dict):
            result.extend(dict_to_shell_vars(value, var_name + "_", export_vars=export_vars,
                                             preprocess_var=preprocess_var))
        else:
            if preprocess_var is not None:
                value, shell_commands = preprocess_var(var_name, value)
                if shell_commands:
                    for shell_command in shell_commands:
                        result.append(shell_command)
            if value is None:
                var_value = None
            elif is_sequence(value):
                var_value = "{}=({})".format(var_name, " ".join([shlex.quote(str(item)) for item in value]))
            else:
                var_value = "{}={}".format(var_name, shlex.quote(str(value)))
            if var_value is not None:
                if export_vars:
                    result.append("export "+var_value)
                else:
                    result.append(var_value)
    return result


def rlinput(prompt, prefill=""):
    readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()


def rlselect(prompt, words, print_menu_on_empty_input=True, print_menu_before_prompt=False, prefill=""):
    value = ""
    while True:
        if print_menu_before_prompt or (print_menu_on_empty_input and value == ""):
            for i, word in enumerate(words):
                print("{}) {}".format(i + 1, word), file=sys.stderr)
        value = rlinput(prompt, prefill=prefill)
        if value == "":
            continue
        try:
            j = int(value)
        except ValueError:
            yield -1, value
        else:
            if j < 1 or j > len(words):
                yield -1, value
            else:
                yield j - 1, words[j - 1]


def select_item(prompt, items, no_query_for_single_item=True):
    if len(items) == 1 and no_query_for_single_item:
        return items[0]

    item = None
    for index, item in rlselect(prompt, list(items) + ["Cancel"]):
        if item == "Cancel":
            LOG.error("User canceled the operation")
            return None
        if index >= 0:
            break
    return item


def randpw(size=16, chars="_" + string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return "".join(random.SystemRandom().choice(chars) for _ in range(size))


def relpaths(base_path, paths, no_parent_dirs=False):
    base_path = os.path.realpath(base_path)
    for path in paths:
        relative_path = os.path.relpath(path, base_path)
        if no_parent_dirs and relative_path.startswith(os.pardir):
            relative_path = os.path.realpath(relative_path)
        yield relative_path


def auto_realpath(path, base_dir, force_abs_path=False):
    if isinstance(path, pathlib.PurePath):
        path = str(path)
    if os.path.isabs(path) and os.path.exists(path):
        path = os.path.realpath(path)
    else:
        if base_dir is None:
            abs_path = path
        else:
            abs_path = os.path.join(base_dir, path)
        if os.path.exists(abs_path):
            path = os.path.realpath(abs_path)
        elif force_abs_path:
            path = abs_path
    return path


def foreach(value, func):
    if not value:
        return []
    if not is_sequence(value):
        return [func(value)]
    return [func(elem) for elem in value]


def realpath_if(path):
    return os.path.realpath(path) if path else path


def array_realpath_if(paths):
    return foreach(paths, realpath_if)


def vault_id_source(vault_id):
    if "@" in vault_id:
        label, source = vault_id.split("@", 1)
        return source
    return None


def vault_id_label(vault_id):
    if "@" in vault_id:
        label, source = vault_id.split("@", 1)
        return label
    return None


def dirname_if(path):
    if path:
        return os.path.dirname(path)
    return path


def array_dirname_if(paths):
    return foreach(paths, dirname_if)


def sep_at_end(path):
    if not path.endswith(os.sep):
        path += os.sep
    return path


def array_sep_at_end(paths):
    return foreach(paths, sep_at_end)


# https://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def which(program):
    def is_executable_file(file_path):
        return os.path.isfile(file_path) and os.access(file_path, os.X_OK)

    fpath, _ = os.path.split(program)
    if fpath:
        if is_executable_file(program):
            return program
    else:
        for path in os.getenv("PATH", "").split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_executable_file(exe_file):
                return exe_file

    return None


def backup_file(path):
    rpath = os.path.realpath(path)
    if os.path.exists(rpath):
        bak_rpath = rpath + "~"
        while os.path.exists(bak_rpath):
            bak_rpath += "~"
        LOG.info("Backup file %s to file %s", rpath, bak_rpath)
        os.rename(rpath, bak_rpath)


def simple_dict_merge(a, b):
    c = {}
    for k, v in a.items():
        if k not in b:
            c[k] = v
        elif isinstance(v, collections.abc.Mapping) and isinstance(b[k], collections.abc.Mapping):
            c[k] = simple_dict_merge(v, b[k])
        else:
            c[k] = b[k]
    for k, v in b.items():
        if k not in a:
            c[k] = v
    return c


def load_config_dict(filename, defaults=None):
    """
    Load configuration from yaml file
    :param filename: YAML file name
    :param defaults: default variables dictionary
    :return: dictionary of loaded variables
    """
    config_dict = {}
    if filename and os.path.exists(filename):
        # noinspection PyBroadException
        try:
            with open(filename, "r", encoding="utf-8") as config_vars_file:
                config_dict = yaml.load(config_vars_file, Loader=Loader)
            if config_dict is None:
                config_dict = {}
            LOG.info("Loaded configuration from file: %s", filename)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Could not load configuration from file: %s", filename)
    if defaults:
        config_dict = simple_dict_merge(defaults, config_dict)
    return config_dict


def save_config_dict(filename, config_dict, do_backup=False):
    if do_backup:
        # noinspection PyBroadException
        try:
            backup_file(filename)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Could not make backup from file: %s", filename)
            return False
    # noinspection PyBroadException
    try:
        with open(filename, "w") as config_vars_file:
            config_vars_file.write(yaml.dump(config_dict, Dumper=Dumper))
        LOG.info("Saved configuration to file: %s", filename)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Could not save vars to file: %s", filename)
        return False

    return True


class VaultId:
    def __init__(self, vault_id=None, base_dir=None, label=None, source=None, apply_realpath=True):
        if vault_id is not None:
            if label is not None or source is not None:
                raise ValueError("label and source arguments cannot be used together with vault_id")
            if "@" in vault_id:
                label, source = vault_id.split("@", 1)
            else:
                label = vault_id
                source = ""
        else:
            if label is None:
                raise ValueError("Neither vault_id nor label arguments are specified")
        self.label = label
        if source and source != "prompt" and apply_realpath:
            source = auto_realpath(source, base_dir=base_dir, force_abs_path=True)
        else:
            source = str(source)
        self.source = source

    def copy(self):
        return VaultId(label=self.label, source=self.source)

    @property
    def id(self):
        return self.label + "@" + self.source

    @property
    def source_is_path(self):
        return self.source and self.source != "prompt"

    @property
    def source_path(self):
        return pathlib.Path(self.source) if self.source_is_path else None

    def relative_to(self, base_dir):
        source_path = self.source_path
        if source_path is not None:
            return VaultId(label=self.label, source=source_path.relative_to(base_dir), apply_realpath=False)
        else:
            return self.copy()

    def __eq__(self, other):
        if isinstance(other, VaultId):
            return self.source == other.source and self.label == other.label
        return False

    def __str__(self):
        return self.id

    def __repr__(self):
        return "VaultId({!r})".format(self.id)


REPLACE_VARS_MERGE_ACTION = '$replace_vars'


class AttrMerger:

    def __init__(self, merge_options: Optional[Mapping[str, str]] = None):
        if not merge_options:
            merge_options = {}
        self.merge_options = merge_options
        self.replace_vars = set(merge_options.get(REPLACE_VARS_MERGE_ACTION, []))
        self.cur_attr_name = ''
        self.attr_name_stack: List[str] = []

    def begin_attr(self, name: str):
        self.attr_name_stack.append(self.cur_attr_name)
        self.cur_attr_name = self.cur_attr_name + '.' + name if self.cur_attr_name else name

    def end_attr(self):
        self.cur_attr_name = self.attr_name_stack.pop()

    def merge_attr(self, this_obj, that_obj, attr_name: str):
        self.begin_attr(attr_name)
        do_replace_attr = self.cur_attr_name in self.replace_vars
        if do_replace_attr:
            setattr(this_obj, attr_name, getattr(that_obj, attr_name))
        else:
            this_value = getattr(this_obj, attr_name)
            that_value = getattr(that_obj, attr_name)
            if isinstance(this_value, collections.abc.Sequence) and \
                    isinstance(that_value, collections.abc.Sequence):
                setattr(this_obj, attr_name, list(this_value) + [item for item in that_value if item not in this_value])
            else:
                setattr(this_obj, attr_name, that_value)
        self.end_attr()


@dataclass
class AnsibleConfig:
    config_file: Optional[pathlib.Path] = None
    inventories: List[pathlib.Path] = field(default_factory=list)
    vault_ids: List[VaultId] = field(default_factory=list)
    vault_password_files: List[pathlib.Path] = field(default_factory=list)
    user_scripts: List[pathlib.Path] = field(default_factory=list)
    vars_files: List[pathlib.Path] = field(default_factory=list)
    vault_files: List[pathlib.Path] = field(default_factory=list)
    private_key_file: Optional[pathlib.Path] = None
    user: Optional[str] = None
    vault_encrypt_identity: Optional[str] = None
    log_path: Optional[pathlib.Path] = None
    env_vars: Dict[str, Any] = field(default_factory=dict)

    def merge(self, other: 'AnsibleConfig', attr_merger: AttrMerger):
        self.config_file = other.config_file
        for attr_name in ('inventories', 'vault_ids', 'vault_password_files',
                          'user_scripts', 'vars_files', 'vault_files', 'env_vars'):
            attr_merger.merge_attr(self, other, attr_name)
        self.private_key_file = other.private_key_file
        self.user = other.user
        self.vault_encrypt_identity = other.vault_encrypt_identity
        self.log_path = other.log_path


@dataclass
class ConfigContext:
    config_file: pathlib.Path
    create_model: bool = True
    serialize_relative_paths: bool = True

    @property
    def config_dir(self):
        return self.config_file.parent


@dataclass
class MainConfig:
    ansible: AnsibleConfig = field(default_factory=lambda: AnsibleConfig())
    config_context: Optional[ConfigContext] = None

    def merge(self, other: 'MainConfig', attr_merger: AttrMerger):
        attr_merger.begin_attr('ansible')
        self.ansible.merge(other.ansible, attr_merger)
        attr_merger.end_attr()
        self.config_context = other.config_context


class PathField(fields.String):
    def _serialize(self, value, attr, obj, **kwargs):
        if self.context.serialize_relative_paths:
            if isinstance(value, pathlib.PurePath):
                try:
                    value = value.relative_to(self.context.config_dir)
                except ValueError:
                    # If we cannot make path relative to the config file use absolute path
                    pass
                value = str(value)
        return super()._serialize(value, attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        svalue = super()._deserialize(value, attr, data, **kwargs)
        return self.context.config_dir / os.path.expanduser(svalue)


class VaultIdField(fields.String):
    def _serialize(self, value, attr, obj, **kwargs):
        if self.context.serialize_relative_paths:
            if isinstance(value, VaultId):
                try:
                    value = value.relative_to(self.context.config_dir)
                except ValueError:
                    # If we cannot make path relative to the config file use absolute path
                    pass
                value = str(value)
        return super()._serialize(value, attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        svalue = super()._deserialize(value, attr, data, **kwargs)
        vault_id = VaultId(svalue)
        source_path = vault_id.source_path
        if source_path:
            source_path = self.context.config_dir / os.path.expanduser(source_path)
            vault_id.source = str(source_path)
        return vault_id


class BaseSchema(Schema):
    # Custom option
    __model__: Any = None

    @post_load
    def make_object(self, data, **kwargs):
        if self.context.create_model and self.__model__ is not None:
            return self.__model__(**data)
        return data

    @post_dump
    def remove_none_values(self, data, **kwargs):
        return {key: value for key, value in data.items() if value is not None}


class AnsibleConfigSchema(BaseSchema):
    __model__ = AnsibleConfig
    config_file = PathField(required=False, allow_none=True)
    inventories = fields.List(PathField, required=False)
    vault_ids = fields.List(VaultIdField, required=False)
    vault_password_files = fields.List(PathField, required=False)
    user_scripts = fields.List(PathField, required=False)
    vars_files = fields.List(PathField, required=False)
    vault_files = fields.List(PathField, required=False)
    private_key_file = PathField(required=False, allow_none=True)
    user = fields.String(required=False, allow_none=True)
    vault_encrypt_identity = fields.String(required=False, allow_none=True)
    log_path = PathField(required=False, allow_none=True)
    env_vars = fields.Dict(keys=fields.Str(), values=fields.Str())


class MainConfigSchema(BaseSchema):
    __model__ = MainConfig
    ansible = fields.Nested(AnsibleConfigSchema, required=False)

    @post_load
    def make_object(self, data, **kwargs):
        if self.context.create_model:
            data["config_context"] = self.context
            return super().make_object(data, **kwargs)
        return data


def pwgen(pwd_file: Optional[str], pwd_length=20):
    if pwd_file and os.path.exists(pwd_file):
        LOG.error("File %s already exists", pwd_file)
        return False
    LOG.info("Generate password of length %s in the file %s", pwd_length, pwd_file)
    if pwd_file:
        with open(pwd_file, "w") as f:
            f.write(randpw(pwd_length))
    else:
        sys.stdout.write(randpw(pwd_length))
    return True


def pwgen_command(args):
    if pwgen(args.output, args.length):
        return 0
    else:
        return 1


def relpath_command(args):
    base_path = os.path.realpath(args.base_path if args.base_path else PROJ_DIR)
    for path in relpaths(base_path=base_path, paths=args.paths, no_parent_dirs=args.no_parent_dirs):
        if args.null:
            print(path, end=chr(0))
        else:
            print(path)
    return 0


ANSIBLE_VAULT_MAGIC = b"$ANSIBLE_VAULT;"


def is_vault(filename):
    if not os.path.exists(filename):
        return False
    with open(filename, "rb") as fd:
        s = fd.read(len(ANSIBLE_VAULT_MAGIC))
        return s == ANSIBLE_VAULT_MAGIC


def find_all_vaults(config):
    found_files = set()
    for filename in config.get_ansible_vault_files():
        if is_vault(filename):
            found_files.add(filename)
            yield filename

    for inventory in config.get_ansible_inventories():
        if not os.path.isdir(inventory):
            inventory_dir = os.path.dirname(inventory)
        else:
            inventory_dir = inventory
        for root, dirs, files in os.walk(inventory_dir, topdown=False, followlinks=False):
            for name in files:
                filename = os.path.join(root, name)
                if filename not in found_files and is_vault(filename):
                    found_files.add(filename)
                    yield filename


def find_all_vaults_command(config, args):
    for filename in find_all_vaults(config):
        if args.null:
            print(filename, end=chr(0))
        else:
            print(filename)
    return 0


# noinspection PyUnusedLocal
def decrypt_all_vaults_command(config, args):
    for filename in find_all_vaults(config):
        print("Decrypting file", filename)
        config.run_ansible_vault("decrypt", vault_file=filename, check_call=True, stderr=sys.stderr)
    return 0


# noinspection PyUnusedLocal
def view_vault_command(config, args):
    vault_files = list(find_all_vaults(config))
    if not vault_files:
        LOG.error("No encrypted ansible vault files found")
        return 1

    vault_fn = select_item("Select ansible vault file to view: ", vault_files)
    if not vault_fn:
        return 1
    return config.run_ansible_vault("view", vault_file=vault_fn, check_call=True)


# noinspection PyUnusedLocal
def decrypt_vault_command(config, args):
    vault_files = list(find_all_vaults(config))
    if not vault_files:
        LOG.error("No ansible vault files found")
        return 1

    vault_fn = select_item("Select ansible vault file to decrypt: ", vault_files)
    if not vault_fn:
        return 1
    return config.run_ansible_vault("decrypt", vault_file=vault_fn, check_call=True)


def encrypt_vault_command(config, args):
    vault_files = [
        filename
        for filename in config.get_ansible_vault_files()
        if (os.path.exists(filename) and not is_vault(filename))
    ]
    if not vault_files:
        LOG.error("No unencrypted ansible vault files found")
        return 1

    vault_fn = select_item("Select ansible vault file to encrypt: ", vault_files)
    if not vault_fn:
        return 1
    LOG.info("Encrypt vault file %s", vault_fn)
    extra_cmd_args = []
    encrypt_vault_id = args and getattr(args, "encrypt_vault_id", None)
    if not encrypt_vault_id and len(config.get_ansible_vault_ids()) > 1:
        encrypt_vault_id = select_item("Select vault id for encryption: ", config.get_ansible_vault_ids())
        if not encrypt_vault_id:
            return 1
        encrypt_vault_id = vault_id_label(encrypt_vault_id)
    if encrypt_vault_id:
        extra_cmd_args.append("--encrypt-vault-id")
        extra_cmd_args.append(encrypt_vault_id)
    return config.run_ansible_vault("encrypt", vault_file=vault_fn, extra_cmd_args=extra_cmd_args, check_call=True)


def edit_vault_command(config, args):
    vault_files = list(find_all_vaults(config))
    if not vault_files:
        if len(config.get_ansible_vault_files()) > 0:
            LOG.warning("No configured ansible vault files exist !: %s", config.get_ansible_vault_files())
            LOG.warning("I will create it !")
            return create_vault_command(config, args)
        LOG.error("No ansible vault files found")
        return 1

    vault_fn = select_item("Select ansible vault file to edit: ", vault_files)
    if not vault_fn:
        return 1
    return config.run_ansible_vault("edit", vault_file=vault_fn, check_call=True)


# noinspection PyUnusedLocal
def create_vault_command(config, args):
    vault_files = [filename for filename in config.get_ansible_vault_files() if not os.path.exists(filename)]
    if not vault_files:
        LOG.error("No ansible vault files configured")
        return 1

    vault_fn = None
    if len(vault_files) == 1:
        vault_fn = vault_files[0]
    else:
        for index, vault_fn in rlselect("Select ansible vault file to create: ", vault_files + ["Cancel"]):
            if vault_fn == "Cancel":
                LOG.error("User canceled the operation")
                return 1
            if index >= 0:
                break
    return config.run_ansible_vault("create", vault_file=vault_fn, check_call=True, stderr=sys.stderr)


def rekey_all_vaults_command(config, args):
    extra_cmd_args = []
    if args.encrypt_vault_id:
        extra_cmd_args.extend(["--encrypt-vault-id", args.encrypt_vault_id])
    if args.new_vault_id:
        extra_cmd_args.extend(["--new-vault-id", args.new_vault_id])
    if args.new_vault_password_file:
        extra_cmd_args.extend(["--new-vault-password-file", args.new_vault_password_file])

    for filename in find_all_vaults(config):
        print("Rekeying file", filename)
        config.run_ansible_vault(
            "rekey", vault_file=filename, extra_cmd_args=extra_cmd_args, check_call=True, stderr=sys.stderr
        )

    return 0


class Configurator:
    def __init__(self, config_files=None, debug_mode=False):
        self.debug_mode = debug_mode
        if config_files:
            config_dict = CONFIG_DEFAULTS

            if len(config_files) == 1:
                config_file = config_files[0]
                config_context = ConfigContext(
                    config_file=pathlib.Path(os.path.realpath(config_file)), create_model=True
                )
                schema = MainConfigSchema()
                schema.context = config_context
                config_dict = load_config_dict(config_file, defaults=config_dict)
                config_model = schema.load(config_dict)
                self._config = config_model

            else:
                merged_config_model = None
                for config_file in config_files:
                    config_context = ConfigContext(
                        config_file=pathlib.Path(os.path.realpath(config_file)),
                        create_model=True,
                    )
                    schema = MainConfigSchema()
                    schema.context = config_context
                    config_dict = load_config_dict(config_file, defaults=config_dict)
                    merge_options = {}
                    # Get merge actions which starts with '$'
                    for merge_action_key in [k for k in config_dict.keys() if k.startswith('$')]:
                        merge_options[merge_action_key] = config_dict.pop(merge_action_key)
                    config_model = schema.load(config_dict)
                    if merged_config_model is None:
                        merged_config_model = config_model
                    else:
                        merged_config_model.merge(config_model, AttrMerger(merge_options=merge_options))

                self._config = merged_config_model
        else:
            self._config = MainConfig()

        self._initial_config_dict = self.config_to_dict()

    def config_to_dict(self):
        config_context = ConfigContext(
            config_file=self._config.config_context.config_file, serialize_relative_paths=False
        )
        schema = MainConfigSchema()
        schema.context = config_context
        return schema.dump(self._config)

    @property
    def config_changed(self):
        return self.config_to_dict() != self._initial_config_dict

    def pprint(self):
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(self._config)

    def save(self, filename=None, force=False, do_backup=False):
        if filename:
            config_context = ConfigContext(config_file=pathlib.Path(os.path.realpath(filename)))
        else:
            if not force:
                if not self.config_changed:
                    return False
                LOG.info("Configuration changed")
            config_context = ConfigContext(config_file=self._config.config_context.config_file)
        schema = MainConfigSchema()
        schema.context = config_context
        serialized_config = schema.dump(self._config)
        return save_config_dict(str(config_context.config_file), serialized_config, do_backup=do_backup)

    def to_shell_vars(self, var_prefix="CFG_"):
        schema = MainConfigSchema()
        schema.context = ConfigContext(
            config_file=self._config.config_context.config_file, serialize_relative_paths=False
        )
        serialized_config = schema.dump(self._config)
        # Process ansible.env_vars differently
        env_vars_config = serialized_config.get('ansible', {}).pop('env_vars', None)
        env_vars = dict_to_shell_vars(env_vars_config, var_prefix='', export_vars=True)

        inventory_dirs = self.get_ansible_inventory_dirs(path_separator_at_end=True)

        def preprocess_shell_var(var_name, value):
            shell_commands = None
            if var_name in ("CFG_ANSIBLE_VARS_FILES", "CFG_ANSIBLE_VAULT_FILES"):
                if var_name == "CFG_ANSIBLE_VARS_FILES":
                    file_type = "variable"
                else:
                    file_type = "vault"
                valid_filenames = []
                shell_commands = []

                for inventory_dir in inventory_dirs:
                    group_vars_dir = sep_at_end(os.path.join(inventory_dir, "group_vars"))
                    host_vars_dir = sep_at_end(os.path.join(inventory_dir, "host_vars"))

                    for filename in value:
                        if filename.startswith(group_vars_dir):
                            shell_commands.append(
                                "# {} {} file is in group_vars inventory directory".format(filename, file_type)
                            )
                        elif filename.startswith(host_vars_dir):
                            shell_commands.append(
                                "# {} {} file is in host_vars inventory directory".format(filename, file_type)
                            )
                        else:
                            valid_filenames.append(filename)
                value = valid_filenames if len(valid_filenames) > 0 else None
            return value, shell_commands

        return dict_to_shell_vars(serialized_config, var_prefix=var_prefix, preprocess_var=preprocess_shell_var)+env_vars

    def get_ansible_user(self) -> Optional[str]:
        return self._config.ansible.user

    def set_ansible_user(self, value: Optional[str]):
        self._config.ansible.user = value

    def get_ansible_private_key_file(self):
        return self._config.ansible.private_key_file

    def set_ansible_private_key_file(self, value):
        self._config.ansible.private_key_file = pathlib.Path(os.path.abspath(value))

    def get_ansible_config_file(self):
        return self._config.ansible.config_file

    def set_ansible_config_file(self, value):
        self._config.ansible.config_file = pathlib.Path(os.path.abspath(value))

    def get_ansible_inventories(self):
        return self._config.ansible.inventories

    def get_ansible_inventory_dirs(self, path_separator_at_end=True):
        inventories = self.get_ansible_inventories()
        result = []
        for inventory in inventories:
            if not inventory:
                continue
            inventory = os.path.realpath(inventory)
            # Inventory can be a file or a directory, if it is not a directory we get a dirname of it
            inventory_dir = os.path.dirname(inventory) if not os.path.isdir(inventory) else inventory
            if path_separator_at_end:
                inventory_dir = sep_at_end(inventory_dir)
            result.append(inventory_dir)
        return result

    def set_ansible_inventories(self, value):
        self._config.ansible.inventories = [pathlib.Path(p) for p in to_abspath_list(value)]

    def get_ansible_vault_password_files(self):
        return self._config.ansible.vault_password_files

    def set_ansible_vault_password_files(self, value):
        self._config.ansible.vault_password_files = [pathlib.Path(p) for p in to_abspath_list(value)]

    def get_ansible_vault_ids(self):
        return self._config.ansible.vault_ids

    def set_ansible_vault_ids(self, value):
        self._config.ansible.vault_ids = [(VaultId(i) if not isinstance(i, VaultId) else i) for i in to_list(value) if
                                          i]

    def get_ansible_vault_encrypt_identity(self):
        return self._config.ansible.vault_encrypt_identity

    def set_ansible_vault_encrypt_identity(self, value):
        self._config.ansible.vault_encrypt_identity = value

    def get_ansible_log_path(self):
        return self._config.ansible.log_path

    def set_ansible_log_path(self, value):
        self._config.ansible.log_path = pathlib.Path(os.path.abspath(value))

    def get_ansible_vault_files(self):
        return self._config.ansible.vault_files

    def set_ansible_vault_files(self, value):
        self._config.ansible.vault_files = [pathlib.Path(p) for p in to_abspath_list(value)]

    def get_ansible_vars_files(self):
        return self._config.ansible.vars_files

    def set_ansible_vars_files(self, value):
        self._config.ansible.vars_files = [pathlib.Path(p) for p in to_abspath_list(value)]

    def add_ansible_vault_password_file_args(self, args):
        for ansible_vault_password_file in self.get_ansible_vault_password_files():
            if os.path.exists(ansible_vault_password_file):
                args.extend(["--vault-password-file", str(ansible_vault_password_file)])
        return args

    def add_ansible_vault_id_args(self, args):
        for ansible_vault_id in self.get_ansible_vault_ids():
            args.extend(["--vault-id", str(ansible_vault_id)])
        return args

    def has_ansible_vault_password_file(self):
        return any(file_name and os.path.exists(file_name) for file_name in self.get_ansible_vault_password_files())

    def get_ansible_user_scripts(self):
        return self._config.ansible.user_scripts

    def set_ansible_user_scripts(self, value):
        self._config.ansible.user_scripts = [pathlib.Path(p) for p in to_abspath_list(value)]

    def get_ansible_env_vars(self):
        return self._config.ansible.env_vars

    def set_ansible_env_vars(self, value):
        self._config.ansible.env_vars = {str(k): v for k, v in value.items()}

    def print_info(self):
        indent = " " * 38
        delim = ",\n" + indent
        print(
            """
    Current Configuration:

    Ansible config file:              {ansible_config_file}
    Ansible inventory file(s):        {ansible_inventories}
    User config directory:            {config_dir}
    Ansible log path:                 {ansible_log_path}
    Ansible vault password file(s):   {ansible_vault_password_files}
    Ansible vault id(s):              {ansible_vault_ids}
    Ansible default vault encrypt id: {ansible_vault_encrypt_identity}
    Ansible remote user:              {ansible_remote_user}
    Ansible private SSH key file:     {ansible_private_key_file}
    Ansible environment vars:         {ansible_env_vars}
    User's ansible vars file(s):      {ansible_vars_files}
    User's ansible vault file(s):     {ansible_vault_files}
    User scripts:                     {ansible_user_scripts}
    """.format(
                ansible_config_file=str(none_to_empty_str(self.get_ansible_config_file())),
                ansible_inventories=delim.join(map(str, self.get_ansible_inventories())),
                ansible_log_path=none_to_empty_str(self.get_ansible_log_path()),
                config_dir=realpath_if(CONFIG_DIR),
                ansible_vault_password_files=delim.join(map(str, self.get_ansible_vault_password_files())),
                ansible_vault_ids=delim.join(map(str, self.get_ansible_vault_ids())),
                ansible_vault_encrypt_identity=none_to_empty_str(self.get_ansible_vault_encrypt_identity()),
                ansible_remote_user=none_to_empty_str(self.get_ansible_user()),
                ansible_private_key_file=str(none_to_empty_str(self.get_ansible_private_key_file())),
                ansible_vars_files=delim.join(map(str, self.get_ansible_vars_files())),
                ansible_vault_files=delim.join(map(str, self.get_ansible_vault_files())),
                ansible_user_scripts=delim.join(map(str, self.get_ansible_user_scripts())),
                ansible_env_vars=delim.join(("{}: {}".format(k, v) for k, v in self.get_ansible_env_vars().items()))
            )
        )

    def print_shell_config(self):
        for shell_var in self.to_shell_vars():
            print(shell_var)

    def print_yaml_config(self):
        config_context = ConfigContext(config_file=self._config.config_context.config_file)
        schema = MainConfigSchema()
        schema.context = config_context
        serialized_config = schema.dump(self._config)
        print(yaml.dump(serialized_config, Dumper=Dumper))

    def has_ansible_vault_files(self):
        return any((vault_fn and os.path.exists(vault_fn)) for vault_fn in self.get_ansible_vault_files())

    def run_ansible_vault(self, command, vault_file, extra_cmd_args=None, check_call=False, stderr=None):
        cmd_args = ["ansible-vault", command]
        self.add_ansible_vault_password_file_args(cmd_args)
        self.add_ansible_vault_id_args(cmd_args)
        cmd_args.append(vault_file)
        if extra_cmd_args:
            cmd_args.extend(extra_cmd_args)

        call_func = subprocess.check_call if check_call else subprocess.call

        LOG.debug("Executing ansible-vault: %s", " ".join((str(arg) for arg in cmd_args)))

        stderr = sys.stderr if self.debug_mode else stderr

        if stderr is None:
            result = call_func(cmd_args, env=os.environ)
        else:
            result = call_func(cmd_args, env=os.environ, stderr=stderr)

        LOG.debug("ansible-vault result: %s", result)
        return result


def process_list_args(set_args: List, add_args: List, remove_args: List, config_get_values_func, value_class: Callable = str):
    new_values: Optional[List[Optional[str]]] = None
    if set_args or remove_args or add_args:
        old_values: List[Optional[str]] = [str_or_none(i) for i in config_get_values_func()]
        if set_args:
            new_values = set_args
        else:
            new_values = old_values[:]
        for item in remove_args:
            if item in new_values:
                new_values.remove(item)
            else:
                _item = str(value_class(item))
                if _item in new_values:
                    new_values.remove(_item)
        for item in add_args:
            _item = str(value_class(item))
            if item not in new_values and _item not in new_values:
                new_values.append(item)
        if new_values == old_values:
            new_values = None
    return new_values


def process_kvlist_args(set_args: List, add_args: List, remove_args: List, config_get_values_func,
                        value_class: Callable = str):
    new_values: Optional[Dict[str, Any]] = None
    if set_args or remove_args or add_args:
        old_values: dict = config_get_values_func()
        if set_args:
            new_values = {str(k):str(v) for k,v in set_args}
        else:
            new_values = old_values.copy()
        for key in remove_args:
            if key in new_values:
                del new_values[key]
            else:
                _key = str(value_class(key))
                if _key in new_values:
                    del new_values[_key]
        for key, value in add_args:
            new_values[key] = value
        if new_values == old_values:
            new_values = None
    return new_values


def main():
    # show_config = False
    # logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
    #                     level=logging.INFO if not show_config else logging.WARNING)
    #
    # configurator = Configurator(config_files=[DEFAULT_CONFIG_FILE, os.path.join(PROJ_DIR, 'data', 'config.yml')])
    # configurator.pprint()
    # # configurator.save()
    # for s in configurator.to_shell_vars():
    #     print(s)

    import argparse
    import copy

    def ensure_value(namespace, name, value):
        if getattr(namespace, name, None) is None:
            setattr(namespace, name, value)
        return getattr(namespace, name)

    class AppendKeyValue(argparse.Action):

        def __init__(self,
                     option_strings,
                     dest,
                     nargs=None,
                     const=None,
                     default=None,
                     type=None,
                     choices=None,
                     required=False,
                     help=None,
                     metavar=None):
            if nargs == 0:
                raise ValueError('nargs for append actions must be > 0; if arg '
                                 'strings are not supplying the value to append, '
                                 'the append const action may be more appropriate')
            if const is not None and nargs != argparse.OPTIONAL:
                raise ValueError('nargs must be %r to supply const' % argparse.OPTIONAL)
            super(AppendKeyValue, self).__init__(
                option_strings=option_strings,
                dest=dest,
                nargs=nargs,
                const=const,
                default=default,
                type=type,
                choices=choices,
                required=required,
                help=help,
                metavar=metavar)

        def __call__(self, parser, namespace, values, option_string=None):
            kv = values.split('=', 1)
            if len(kv) == 1:
                kv.append('')

            items = copy.copy(ensure_value(namespace, self.dest, []))
            items.append(kv)
            setattr(namespace, self.dest, items)

    class StoreNameValuePair(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            n, v = values.split('=')
            setattr(namespace, n, v)

    parser = argparse.ArgumentParser(description="Ansible configurator")
    parser.add_argument(
        "-c",
        "--config",
        default=[],
        metavar="CONFIG_FILE",
        dest="config_files",
        help="additional config files",
        action="append",
    )
    parser.add_argument("--read-only", help="do not change configuration or variable files", action="store_true")
    parser.add_argument("--debug", help="debug mode", action="store_true")
    parser.add_argument("--no-backup", help="disable backup", action="store_true")
    parser.add_argument(
        "-i", "--inventory", action="append", help="specify inventory host path or comma separated host list"
    )

    parser.add_argument("--vault", default=[], dest="vault_files", help="vault file", action="append")
    parser.add_argument(
        "--add-vault", "--add-vault-file", default=[], dest="add_vault_files", help="add vault files", action="append"
    )
    parser.add_argument(
        "--remove-vault",
        "--remove-vault-file",
        default=[],
        dest="remove_vault_files",
        help="remove vault files",
        action="append",
    )

    parser.add_argument("--vars", default=[], dest="vars_files", help="vars file", action="append")
    parser.add_argument("--add-vars", default=[], dest="add_vars_files", help="add vars files", action="append")
    parser.add_argument(
        "--remove-vars", default=[], dest="remove_vars_files", help="remove vars files", action="append"
    )

    parser.add_argument(
        "--pwgen", metavar="FILE", dest="pwd_file", help="generate random password, store to file and exit"
    )
    parser.add_argument("-u", "--user", default=None, help="set remote user")
    parser.add_argument("-r", "--reconfigure", help="reconfigure", action="store_true")
    parser.add_argument("-k", "--private-key", default=None, dest="private_key", help="set private key filename")
    parser.add_argument(
        "--shell-config",
        help="print configuration variables in Bash-compatible script format and exit",
        action="store_true",
    )
    parser.add_argument(
        "--yaml-config", help="print configuration variables in YAML format and exit", action="store_true"
    )
    parser.add_argument("--pretty-config", help="pretty print configuration variables", action="store_true")
    parser.add_argument("--show", help="print info and exit", action="store_true")
    parser.add_argument("-v", "--view-vault", help="view configuration vault and exit", action="store_true")
    parser.add_argument("--decrypt-vault", help="decrypt vault and exit", action="store_true")
    parser.add_argument("--edit-vault", help="edit vault and exit", action="store_true")
    parser.add_argument("--encrypt-vault", help="encrypt vault and exit", action="store_true")
    parser.add_argument(
        "--vault-password-file", default=[], dest="vault_password_files", help="vault password file", action="append"
    )
    parser.add_argument(
        "--add-vault-password-file",
        default=[],
        dest="add_vault_password_files",
        help="add vault password files",
        action="append",
    )
    parser.add_argument(
        "--remove-vault-password-file",
        default=[],
        dest="remove_vault_password_files",
        help="remove vault password files",
        action="append",
    )
    parser.add_argument("--vault-id", default=[], dest="vault_ids", help="vault ID", action="append")
    parser.add_argument("--add-vault-id", default=[], dest="add_vault_ids", help="add vault IDs", action="append")
    parser.add_argument(
        "--remove-vault-id", default=[], dest="remove_vault_ids", help="remove vault IDs", action="append"
    )
    parser.add_argument("--env-var", default=[], dest="env_vars", metavar="VAR=VALUE", help="environment variable",
                        action=AppendKeyValue)
    parser.add_argument("--add-env-var", default=[], dest="add_env_vars", metavar="VAR=VALUE",
                        help="add environment variable",
                        action=AppendKeyValue)
    parser.add_argument(
        "--remove-env-var", default=[], dest="remove_env_vars", metavar="VAR", help="remove environment variable",
        action="append"
    )

    parser.add_argument("--user-script", default=[], dest="user_scripts", help="user script", action="append")
    parser.add_argument(
        "--add-user-script", default=[], dest="add_user_scripts", help="add user scripts", action="append"
    )
    parser.add_argument(
        "--remove-user-script", default=[], dest="remove_user_scripts", help="remove user scripts", action="append"
    )

    parser.add_argument("--default-vault-encrypt-id", default=None, help="set default vault encrypt identity")
    parser.add_argument("--default-log-path", default=None, help="set default log path")
    parser.set_defaults(func=None)
    parser.set_defaults(func_require_config=True)

    subparsers = parser.add_subparsers(title="subcommands", dest="subcommand", metavar="")

    command_p = subparsers.add_parser("pwgen", help="Generate password and save to file")
    command_p.add_argument("-o", "--output", metavar="FILE", help="password file name")
    command_p.add_argument("-n", "--length", metavar="PASSWORD_LENGTH", type=int, default=20, help="password length")
    command_p.set_defaults(func_require_config=False)
    command_p.set_defaults(func=pwgen_command)

    command_p = subparsers.add_parser("relpath", help="Relativize paths")
    command_p.add_argument(
        "-b", "--base-path", help="base path, by default path to the directory where config.yml is located"
    )
    command_p.add_argument(
        "-p",
        "--no-parent-dirs",
        action="store_true",
        help="Use absolute paths instead of using parent directories (..)",
    )
    command_p.add_argument(
        "-0",
        "--null",
        action="store_true",
        help="""print the full path name on the standard output, followed by a null
    character. This allows path names that  contain newlines or other types of white space to be correctly
    interpreted by programs that process the output. This option corresponds to the -0 option of xargs.""",
    )
    command_p.add_argument("paths", metavar="PATH", nargs="+", help="path to relativize")
    command_p.set_defaults(func_require_config=False)
    command_p.set_defaults(func=relpath_command)

    command_p = subparsers.add_parser("find-all-vaults", help="find all vault files")
    command_p.add_argument(
        "-0",
        "--null",
        action="store_true",
        help="""print the full file name on the standard output, followed by a null
    character. This allows file names that  contain newlines or other types of white space to be correctly
    interpreted by programs that process the output. This option corresponds to the -0 option of xargs.""",
    )
    command_p.set_defaults(func=find_all_vaults_command)

    command_p = subparsers.add_parser("decrypt-all-vaults", help="decrypt all vault files")
    command_p.set_defaults(func=decrypt_all_vaults_command)

    command_p = subparsers.add_parser("encrypt-vault", help="encrypt vault file")
    command_p.add_argument(
        "--encrypt-vault-id", help="the vault id used to encrypt (required if more than vault-id " "is provided)"
    )
    command_p.set_defaults(func=encrypt_vault_command)

    command_p = subparsers.add_parser("rekey-vaults", help="rekey all vault files")
    command_p.add_argument(
        "--encrypt-vault-id", help="the vault id used to encrypt (required if more than vault-id is provided)"
    )
    command_p.add_argument("--new-vault-id", help="the new vault identity to use for rekey")
    command_p.add_argument("--new-vault-password-file", help="new vault password file for rekey")
    command_p.set_defaults(func=rekey_all_vaults_command)

    args = parser.parse_args()

    show_config = args.shell_config or args.yaml_config or args.pretty_config

    if args.debug:
        logging.basicConfig(
            format="%(asctime)s %(levelname)s %(pathname)s:%(lineno)s: %(message)s", level=logging.DEBUG
        )
    else:
        logging.basicConfig(
            format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO if not show_config else logging.WARNING
        )

    if args.func is not None and not args.func_require_config:
        return args.func(args=args)

    if args.pwd_file:
        if args.read_only:
            LOG.error("Password generation cannot be performed in read-only mode")
            return 1
        if pwgen(args.pwd_file):
            return 0
        else:
            return 1

    # Check for ansible tools
    tool_not_found = False
    for tool in ("ansible", "ansible-vault", "ansible-playbook", "ansible-inventory"):
        tool_path = which(tool)
        if not tool_path:
            LOG.error("Ansible tool '%s' was not found in PATH", tool)
            tool_not_found = True
    if tool_not_found:
        LOG.error(
            "Some Ansible tools were not found in PATH environment variable, either Ansible was not installed "
            "or it was not added to PATH."
        )
        LOG.error("PATH: %s", os.getenv("PATH", None))
        return 1

    # Load configuration
    config_files = args.config_files or [DEFAULT_CONFIG_FILE]
    try:
        config = Configurator(config_files=config_files, debug_mode=args.debug)
    except Exception:
        LOG.exception("Could not create configuration from files: %s", ", ".join(config_files))
        return 1

    if args.func is not None:
        return args.func(config=config, args=args)

    if not args.inventory:
        args.inventory = [str(i) for i in config.get_ansible_inventories()]

    new_vars_files = process_list_args(
        args.vars_files, args.add_vars_files, args.remove_vars_files,
        config.get_ansible_vars_files, realpath_if)

    new_vault_files = process_list_args(
        args.vault_files, args.add_vault_files, args.remove_vault_files,
        config.get_ansible_vault_files, realpath_if)

    if args.user is None:
        args.user = str_or_none(config.get_ansible_user())
    if args.private_key is None:
        args.private_key = str_or_none(config.get_ansible_private_key_file())

    new_vault_password_files = process_list_args(
        args.vault_password_files, args.add_vault_password_files, args.remove_vault_password_files,
        config.get_ansible_vault_password_files, realpath_if)

    new_vault_ids = process_list_args(
        args.vault_ids, args.add_vault_ids, args.remove_vault_ids,
        config.get_ansible_vault_ids, VaultId)

    new_env_vars = process_kvlist_args(
        args.env_vars, args.add_env_vars, args.remove_env_vars,
        config.get_ansible_env_vars
    )

    new_user_scripts = process_list_args(
        args.user_scripts, args.add_user_scripts, args.remove_user_scripts,
        config.get_ansible_user_scripts, realpath_if)

    if args.default_vault_encrypt_id is None:
        args.default_vault_encrypt_id = config.get_ansible_vault_encrypt_identity()

    if args.default_log_path is None:
        args.default_log_path = config.get_ansible_log_path()

    if args.shell_config:
        config.print_shell_config()
        return 0

    if args.yaml_config:
        config.print_yaml_config()
        return 0

    if args.pretty_config:
        config.pprint()
        return 0

    if args.show:
        config.print_info()
        return 0

    readline.parse_and_bind("tab: complete")

    if args.view_vault:
        return view_vault_command(config, args)

    if args.decrypt_vault:
        return decrypt_vault_command(config, args)

    if args.encrypt_vault:
        return encrypt_vault_command(config, args)

    if args.edit_vault:
        return edit_vault_command(config, args)

    if not args.read_only and not os.path.isdir(CONFIG_DIR):
        LOG.info("Create directory: %r", CONFIG_DIR)
        os.makedirs(CONFIG_DIR)

    if not args.read_only and not config.has_ansible_vault_password_file():
        found_file_name = None
        for file_name in config.get_ansible_vault_password_files():
            if file_name:
                found_file_name = file_name
                break
        if found_file_name:
            LOG.info("Generate vault password file: %r", found_file_name)
            with open(found_file_name, "w") as pwd_file:
                pwd_file.write(randpw())

    if args.reconfigure:
        if args.read_only:
            LOG.error("Reconfiguration cannot be performed in read-only mode")
            return 1
        user = rlinput("Ansible user name: ", config.get_ansible_user())
        args.user = user

    if args.user != str_or_none(config.get_ansible_user()):
        config.set_ansible_user(args.user)
        LOG.info("Ansible user set to %r", config.get_ansible_user())

    if args.private_key != str_or_none(config.get_ansible_private_key_file()):
        config.set_ansible_private_key_file(args.private_key)
        LOG.info("Set ansible private key file to %r", args.private_key)

    if array_realpath_if(args.inventory) != [str_or_none(i) for i in config.get_ansible_inventories()]:
        config.set_ansible_inventories(args.inventory)
        LOG.info("Set ansible inventory file(s) to %s", ", ".join(map(str, args.inventory)))

    if new_vault_password_files is not None:
        config.set_ansible_vault_password_files(new_vault_password_files)
        LOG.info("Set ansible vault password files to %r", new_vault_password_files)

    if new_vault_ids is not None:
        config.set_ansible_vault_ids(new_vault_ids)
        LOG.info("Set ansible vault ids to %r", new_vault_ids)

    if new_env_vars is not None:
        config.set_ansible_env_vars(new_env_vars)
        LOG.info("Set ansible environment vars to %r", new_env_vars)

    if new_user_scripts is not None:
        config.set_ansible_user_scripts(new_user_scripts)
        LOG.info("Set ansible user scripts to %r", new_user_scripts)

    if new_vars_files is not None:
        config.set_ansible_vars_files(new_vars_files)
        LOG.info("Set user's ansible vars files to %r", new_vars_files)

    if new_vault_files is not None:
        config.set_ansible_vault_files(new_vault_files)
        LOG.info("Set user's ansible vault files to %r", new_vault_files)

    if args.default_vault_encrypt_id != str_or_none(config.get_ansible_vault_encrypt_identity()):
        config.set_ansible_vault_encrypt_identity(
            args.default_vault_encrypt_id if args.default_vault_encrypt_id else None
        )
        LOG.info("Set default ansible encrypt identity to %r", config.get_ansible_vault_encrypt_identity())

    if args.default_log_path != str_or_none(config.get_ansible_log_path()):
        config.set_ansible_log_path(args.default_log_path if args.default_log_path else None)
        LOG.info("Set default ansible log path to %r", config.get_ansible_log_path())

    if args.reconfigure:
        if args.read_only:
            LOG.error("Reconfiguration cannot be performed in read-only mode")
            return 1
        count = 0
        while True:
            if count > 2:
                print("Have exhausted maximum number of retries", file=sys.stderr)
                return 1
            sudo_pass_1 = getpass.getpass("Sudo password: ")
            sudo_pass_2 = getpass.getpass("Retype sudo password: ")
            if sudo_pass_1 != sudo_pass_2:
                print("Sorry, passwords do not match", file=sys.stderr)
            else:
                break
            count += 1
        vault_data = {"ansible_become_pass": sudo_pass_1}
        vault_filename = select_item("Select vault file to write password to: ", config.get_ansible_vault_files())
        if vault_filename is None:
            return 1
        with open(vault_filename, "w") as vault_file:
            vault_file.write(yaml.dump(vault_data, Dumper=Dumper))
        LOG.info("Wrote sudo password to vault file: %s", vault_filename)

    for vault_filename in config.get_ansible_vault_files():
        if not os.path.exists(vault_filename):
            LOG.warning("Vault file {} is configured but does not exist !".format(vault_filename))

        elif not is_vault(vault_filename):
            LOG.warning(
                'Vault file {} is configured, but not encrypted ! Execute the command "ansible-vault encrypt" '
                "to encrypt it !".format(vault_filename)
            )
            # config.run_ansible_vault('encrypt', check_call=False, stderr=DEVNULL)

    if not args.read_only:
        config.save(do_backup=not args.no_backup)
        LOG.info("Configuration finished")

    config.print_info()

    return 0


if __name__ == "__main__":
    sys.exit(main())
