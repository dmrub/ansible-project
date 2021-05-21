#!/usr/bin/env python

from __future__ import print_function
import json
import sys
import argparse
import copy
import os.path

def main():
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

    parser = argparse.ArgumentParser(description="SSH option parser")
    parser.add_argument('-4', dest='AddressFamily', const='inet', action="store_const",
                        help='Forces ssh to use IPv4 addresses only.')
    parser.add_argument('-6', dest='AddressFamily', action="store_const", const='inet6',
                        help='Forces ssh to use IPv6 addresses only.')
    parser.add_argument('-A', dest='ForwardAgent', action="store_const", const="yes",
                        help='Enables forwarding of the authentication agent connection.')
    parser.add_argument('-a', dest='ForwardAgent', action="store_const", const="no",
                        help='Disables forwarding of the authentication agent connection.')
    parser.add_argument('-B', dest="bind_interface", metavar="bind_interface", action="store",
                        help='Bind to the address of bind_interface before attempting to connect to the destination '
                             'host.')
    parser.add_argument('-b', dest="bind_address", metavar="bind_address", action="store",
                        help='Use bind_address on the local machine as the source address of the connection.')
    parser.add_argument('-C', dest="Compression", action="store_const", const="yes",
                        help="Requests compression of all data")
    parser.add_argument('-c', dest="Ciphers", action="store", metavar='cipher_spec',
                        help="Selects the cipher specification for encrypting the session.")
    parser.add_argument('-D', dest='DynamicForward', metavar='bind_address_and_port', action='append',
                        help="Specifies a local dynamic application-level port forwarding.")
    parser.add_argument('-E', dest='log_file', metavar='log_file', action='store',
                        help="Append debug logs to log_file instead of standard error.")
    parser.add_argument('-e', dest='escape_char', metavar='escape_char', action='store',
                        help="Sets the escape character for sessions with a pty (default: '~').")
    parser.add_argument('-F', dest='configfile', metavar='configfile', action='store',
                        help="Specifies an alternative per-user configuration file.")
    parser.add_argument('-f', dest='go_to_background', action='store_true',
                        help="Requests ssh to go to background just before command execution.")
    parser.add_argument('-G', dest='print_config', action='store_true',
                        help="Causes ssh to print its configuration after evaluating Host and Match blocks and exit.")
    parser.add_argument('-g', dest='allow_connect_to_local_forwarded_ports', action='store_true',
                        help="Allows remote hosts to connect to local forwarded ports.")

    parser.add_argument('-I', dest='pkcs11', metavar='pkcs11', action='store',
                        help="Specify the PKCS#11 shared library ssh should use to communicate with a PKCS#11 token "
                             "providing the user's private RSA key.")
    parser.add_argument('-i', dest='identity_file', metavar='identity_file', action='store',
                        help="Selects a file from which the identity (private key) for public key authentication is "
                             "read.")
    parser.add_argument('-J', dest='destination', metavar='destination', action='store',
                        help="Connect to the target host by first making a ssh connection to the jump host described "
                             "by destination and then establishing a TCP forwarding to the ultimate destination from "
                             "there.")
    parser.add_argument('-K', dest='gssapi_authentication_and_delegation', action='store_true',
                        help="Enables GSSAPI-based authentication and forwarding (delegation) of GSSAPI credentials "
                             "to the server.")
    parser.add_argument('-k', dest='gssapi_authentication_and_delegation', action='store_false',
                        help="Disables forwarding (delegation) of GSSAPI credentials to the server.")
    parser.add_argument('-L', dest='LocalForward', metavar='bind_address_port_and_host', action='append',
                        help="Specifies that connections to the given TCP port or Unix socket on the local (client) "
                             "host are to be forwarded to the given host and port, or Unix socket, on the remote "
                             "side.")
    parser.add_argument('-l', dest='login_name', metavar='login_name', action='store',
                        help="Specifies the user to log in as on the remote machine.")
    parser.add_argument('-M', dest='control_master_mode', action='count',
                        help="Places the ssh client into \"master\" mode for connection sharing.  Multiple -M options "
                             "places ssh into \"master\" mode with confirmation required before slave connections are "
                             "accepted.")
    parser.add_argument('-m', dest='MACs', metavar='mac_spec', action='store',
                        help="A comma-separated list of MAC (message authentication code) algorithms, specified in "
                             "order of preference.")
    parser.add_argument('-N', dest='dont_execute_remote_command', action='store_true',
                        help="Do not execute a remote command.")
    parser.add_argument('-n', dest='redirect_stdin', action='store_true',
                        help="Redirects stdin from /dev/null (actually, prevents reading from stdin).")
    parser.add_argument('-O', dest='ctl_cmd', metavar='ctl_cmd', action='store',
                        help='Control an active connection multiplexing master process.')
    parser.add_argument('-o', dest='option', metavar='option', action=AppendKeyValue,
                        help='Control an active connection multiplexing master process.')
    parser.add_argument('-p', dest='Port', metavar='port', action='store',
                        help='Port to connect to on the remote host.')
    parser.add_argument('-Q', dest='query_option', metavar='query_option', action='store',
                        help='Queries ssh for the algorithms supported for the specified version 2.')
    parser.add_argument('-q', dest='LogLevel', action='store_const', const='QUIET',
                        help='Quiet mode.')
    parser.add_argument('-R', dest='RemoteForward', metavar='bind_address_port_and_host', action='append',
                        help="Specifies that connections to the given TCP port or Unix socket on the remote (server) "
                             "host are to be forwarded to the local side.")
    parser.add_argument('-S', dest='ControlPath', metavar='ctl_path', action='store',
                        help='Specifies the location of a control socket for connection sharing, or the string '
                             '\"none\" to disable connection sharing.')
    parser.add_argument('-s', dest='request_subsystem', action='store_true',
                        help='May be used to request invocation of a subsystem on the remote system.  Subsystems '
                             'facilitate the use of SSH as a secure transport for other applications (e.g. sftp(1)).')
    parser.add_argument('-T', dest='request_tty', action='store_const', const=0,
                        help='Disable pseudo-terminal allocation.')
    parser.add_argument('-t', dest='request_tty', action='count',
                        help='Force pseudo-terminal allocation.')
    parser.add_argument('-V', dest='show_version', action='store_true', help='Display the version number and exit.')
    parser.add_argument('-v', dest='verbose', action='count', help='Verbose mode.')
    parser.add_argument('-W', dest='forward_io', metavar='host:port', action='store',
                        help="Requests that standard input and output on the client be forwarded to host on port over "
                             "the secure channel.")
    parser.add_argument('-w', dest='TunnelDevice', metavar='local_tun:remote_tun', action='store',
                        help="Requests tunnel device forwarding with the specified tun(4) devices between the client "
                             "(local_tun) and the server (remote_tun).")
    parser.add_argument('-X', dest='ForwardX11', action='store_const', const='yes',
                        help="Enables X11 forwarding.")
    parser.add_argument('-x', dest='ForwardX11', action='store_const', const='no',
                        help="Disables X11 forwarding.")
    parser.add_argument('-Y', dest='ForwardX11Trusted', action='store_const', const='yes',
                        help="Enables trusted X11 forwarding.")
    parser.add_argument('-y', dest='use_syslog', action='store_true',
                        help="Send log information using the syslog(3) system module.")
    parser.add_argument('--dest-dir', metavar='dest_dir', action='store',
                        help="Destination directory of the SSH config file used for path resolution")

    #print(repr(sys.argv[1:]), file=sys.stderr)
    args = parser.parse_args()

    # TODO: Implement conversion of all SSH command line options to ssh_config format

    ssh_config = []
    ssh_keys = set()
    def update_ssh_config(key, value):
        if '{{' in value or '{%' in value:
            ssh_config.append('# Error: ansible variable used for SSH option "{}" cannot be evaluated'.format(key))
            return
        ssh_keys.add(key)
        if ' ' in value:
            ssh_config.append('{}={}'.format(key, value))
        else:
            ssh_config.append('{} {}'.format(key, value))

    if args.option:
        for key, value in args.option:
            update_ssh_config(key, value)

    if args.identity_file:
        identity_file = args.identity_file
        if not os.path.isabs(identity_file):
            if args.dest_dir:
                identity_file = os.path.abspath(os.path.join(args.dest_dir, identity_file))
        update_ssh_config('IdentityFile', identity_file)

    for i in ssh_config:
        print(i)


if __name__ == "__main__":
    sys.exit(main())
