import crypt
import logging

from tests.common.errors import RunAnsibleModuleFail
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

def check_output(output, exp_val1, exp_val2):
    pytest_assert(not output['failed'], output['stderr'])
    for l in output['stdout_lines']:
        fds = l.split(':')
        if fds[0] == exp_val1:
            pytest_assert(fds[4] == exp_val2)

def check_all_services_status(ptfhost):
    res = ptfhost.command("service --status-all")
    logger.info(res["stdout_lines"])


def start_tacacs_server(ptfhost):
    ptfhost.command("service tacacs_plus restart", module_ignore_errors=True)
    return "tacacs+ running" in ptfhost.command("service tacacs_plus status", module_ignore_errors=True)["stdout_lines"]

def stop_tacacs_server(ptfhost):
    ptfhost.service(name="tacacs_plus", state="stopped")
    check_all_services_status(ptfhost)

def setup_local_user(duthost, creds_all_duts):
    try:
        duthost.shell("sudo deluser {}".format(creds_all_duts[duthost]['local_user']))
    except RunAnsibleModuleFail:
        logger.info("local user not exist")
    
    duthost.shell("sudo useradd {}".format(creds_all_duts[duthost]['local_user']))
    duthost.shell('sudo echo "{}:{}" | chpasswd'.format(creds_all_duts[duthost]['local_user'],creds_all_duts[duthost]['local_user_passwd']))

def setup_tacacs_client(duthost, creds_all_duts, tacacs_server_ip):
    """setup tacacs client"""

    # configure tacacs client
    duthost.shell("sudo config tacacs passkey %s" % creds_all_duts[duthost]['tacacs_passkey'])

    # get default tacacs servers
    config_facts = duthost.config_facts(host=duthost.hostname, source="running")['ansible_facts']
    for tacacs_server in config_facts.get('TACPLUS_SERVER', {}):
        duthost.shell("sudo config tacacs delete %s" % tacacs_server)
    duthost.shell("sudo config tacacs add %s" % tacacs_server_ip)
    duthost.shell("sudo config tacacs authtype login")

    # enable tacacs+
    duthost.shell("sudo config aaa authentication login tacacs+")
    duthost.shell("sudo config aaa authorization local")
    duthost.shell("sudo config aaa accounting disable")
    
    # setup local user
    setup_local_user(duthost, creds_all_duts)


def setup_tacacs_server(ptfhost, creds_all_duts, duthost):
    """setup tacacs server"""

    # configure tacacs server
    extra_vars = {'tacacs_passkey': creds_all_duts[duthost]['tacacs_passkey'],
                  'tacacs_rw_user': creds_all_duts[duthost]['tacacs_rw_user'],
                  'tacacs_rw_user_passwd': crypt.crypt(creds_all_duts[duthost]['tacacs_rw_user_passwd'], 'abc'),
                  'tacacs_ro_user': creds_all_duts[duthost]['tacacs_ro_user'],
                  'tacacs_ro_user_passwd': crypt.crypt(creds_all_duts[duthost]['tacacs_ro_user_passwd'], 'abc'),
                  'tacacs_authorization_user': creds_all_duts[duthost]['tacacs_authorization_user'],
                  'tacacs_authorization_user_passwd': crypt.crypt(creds_all_duts[duthost]['tacacs_authorization_user_passwd'], 'abc'),
                  'tacacs_jit_user': creds_all_duts[duthost]['tacacs_jit_user'],
                  'tacacs_jit_user_passwd': crypt.crypt(creds_all_duts[duthost]['tacacs_jit_user_passwd'], 'abc'),
                  'tacacs_jit_user_membership': creds_all_duts[duthost]['tacacs_jit_user_membership']}

    ptfhost.host.options['variable_manager'].extra_vars.update(extra_vars)
    # Fix python version, because tac_plus server not support regex in command name, and SONiC will send full path to tacacs server side for authorization
    ptfhost.template(src="tacacs/tac_plus.conf.j2", dest="/etc/tacacs+/tac_plus.conf")
    # Get max version of python.
    python_with_version = duthost.shell('ls /usr/bin/ | grep python[0-9]\\\\.[0-9]*$ | tail -1')['stdout']
    ptfhost.shell("sed -i 's/python/{0}/g' /etc/tacacs+/tac_plus.conf".format(python_with_version))

    # Get max version of ld lib.
    ld_with_version = duthost.shell('ls /lib/x86_64-linux-gnu/ | grep ld-[0-9\\.]*\\.so | tail -1')['stdout']
    ptfhost.shell("sed -i 's/ld-version.so/{0}/g' /etc/tacacs+/tac_plus.conf".format(ld_with_version))
    
    ptfhost.lineinfile(path="/etc/default/tacacs+", line="DAEMON_OPTS=\"-d 10 -l /var/log/tac_plus.log -C /etc/tacacs+/tac_plus.conf\"", regexp='^DAEMON_OPTS=.*')
    check_all_services_status(ptfhost)

    # FIXME: This is a short term mitigation, we need to figure out why the tacacs+ server does not start
    # reliably all of a sudden.
    wait_until(5, 1, 0, start_tacacs_server, ptfhost)
    check_all_services_status(ptfhost)


def cleanup_tacacs(ptfhost, duthost, tacacs_server_ip):
    # stop tacacs server
    stop_tacacs_server(ptfhost)

    # reset tacacs client configuration
    duthost.shell("sudo config tacacs delete %s" % tacacs_server_ip)
    duthost.shell("sudo config tacacs default passkey")
    duthost.shell("sudo config aaa authentication login default")
    duthost.shell("sudo config aaa authentication failthrough default")
    duthost.shell("sudo config aaa authorization local")
    duthost.shell("sudo config aaa accounting disable")
