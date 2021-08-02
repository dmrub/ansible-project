#!/usr/bin/env python

# Copyright: (c) 2020, Dmitri Rubinstein
# Apache 2.0 License, http://www.apache.org/licenses/
from __future__ import absolute_import, division, print_function
import sys
import os
import os.path

__metaclass__ = type

DOCUMENTATION = r"""
---
module: python_script

short_description: Evaluate python code

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description:
    - This C(python_script) module allows to manipulate ansible facts with python instead of jinja

options:
  script:
    description: Python script code
    type: str
    version_added: '1.1'

  script_args:
      description: This is argument to the python code
      required: false
      type: raw
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
extends_documentation_fragment:
    - dmrub.util.python_script

author:
    - Dmitri Rubinstein (@dmrub)
"""

EXAMPLES = r"""
# Pass in string
- name: Test with string
  python_script:
    script_args: hello world
    script: |
        result["script_args"] = 'goodbye'
        result["changed"] = True
"""

RETURN = r"""
# These are examples of possible return values, and in general should use other names for return values.
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_bytes, to_native
from ansible.module_utils.six import PY3


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        script=dict(type="str", no_log=True, required=True),
        script_args=dict(type="raw", required=False),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any script_args that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    script = module.params["script"]

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    exec_globals = globals()
    exec_globals["module"] = module
    exec_globals["result"] = result

    exec(script, exec_globals)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    # result['original_message'] = module.params['name']
    # result['message'] = 'goodbye'

    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    # if module.params['new']:
    #    result['changed'] = True

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    # if module.params['name'] == 'fail me':
    #    module.fail_json(msg='You requested this to fail', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
