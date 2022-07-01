import json
import logging
import os
import pytest
import random
import time
import yaml

from collections import defaultdict

from jinja2 import Template
from tests.common.helpers.assertions import pytest_assert
from tests.common.helpers.assertions import pytest_require
from tests.common.helpers.buffer import update_cable_len
from tests.common import config_reload
from tests.common.dualtor.constants import UPPER_TOR, LOWER_TOR
from tests.common.helpers.dut_utils import verify_features_state
from tests.common.utilities import wait_until
from tests.common.reboot import reboot
from tests.common.platform.processes_utils import wait_critical_processes
from tests.common.utilities import get_host_visible_vars

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.pretest,
    pytest.mark.topology('util'),
    pytest.mark.disable_loganalyzer
]


FEATURE_STATE_VERIFYING_THRESHOLD_SECS = 600
FEATURE_STATE_VERIFYING_INTERVAL_SECS = 10


def test_features_state(duthosts, enum_dut_hostname, localhost):
    """Checks whether the state of each feature is valid or not.
    Args:
      duthosts: Fixture returns a list of Ansible object DuT.
      enum_dut_hostname: Fixture returns name of DuT.

    Returns:
      None.
    """
    duthost = duthosts[enum_dut_hostname]
    logger.info("Checking the state of each feature in 'CONFIG_DB' ...")
    if not wait_until(180, FEATURE_STATE_VERIFYING_INTERVAL_SECS, 0, verify_features_state, duthost):
        logger.warn("Not all states of features in 'CONFIG_DB' are valid, rebooting DUT {}".format(duthost.hostname))
        reboot(duthost, localhost)
        # Some services are not ready immeidately after reboot
        wait_critical_processes(duthost)

    pytest_assert(wait_until(FEATURE_STATE_VERIFYING_THRESHOLD_SECS, FEATURE_STATE_VERIFYING_INTERVAL_SECS, 0,
                             verify_features_state, duthost), "Not all service states are valid!")
    logger.info("The states of features in 'CONFIG_DB' are all valid.")

def test_cleanup_cache():
    folder = '_cache'
    if os.path.exists(folder):
        os.system('rm -rf {}'.format(folder))


def test_cleanup_testbed(duthosts, enum_dut_hostname, request, ptfhost):
    duthost = duthosts[enum_dut_hostname]
    deep_clean = request.config.getoption("--deep_clean")
    if deep_clean:
        logger.info("Deep cleaning DUT {}".format(duthost.hostname))
        # Remove old log files.
        duthost.shell("sudo find /var/log/ -name '*.gz' | sudo xargs rm -f", executable="/bin/bash")
        # Remove old core files.
        duthost.shell("sudo rm -f /var/core/*", executable="/bin/bash")
        # Remove old dump files.
        duthost.shell("sudo rm -rf /var/dump/*", executable="/bin/bash")

        # delete other log files that are more than a day old,
        # this step is needed to remove some backup files or the debug files added by users
        # which can create issue for log-analyzer
        duthost.shell("sudo find /var/log/ -mtime +1 | sudo xargs rm -f",
            module_ignore_errors=True, executable="/bin/bash")

    # Cleanup rsyslog configuration file that might have damaged by test_syslog.py
    if ptfhost:
        ptfhost.shell("if [[ -f /etc/rsyslog.conf ]]; then mv /etc/rsyslog.conf /etc/rsyslog.conf.orig; uniq /etc/rsyslog.conf.orig > /etc/rsyslog.conf; fi", executable="/bin/bash")


def test_disable_container_autorestart(duthosts, enum_dut_hostname, disable_container_autorestart):
    duthost = duthosts[enum_dut_hostname]
    disable_container_autorestart(duthost)
    # Wait sometime for snmp reloading
    SNMP_RELOADING_TIME = 30
    time.sleep(SNMP_RELOADING_TIME)


def collect_dut_info(dut):
    status = dut.show_interface(command='status')['ansible_facts']['int_status']
    features, _ = dut.get_feature_status()

    if dut.sonichost.is_multi_asic:
        front_end_asics = dut.get_frontend_asic_ids()
        back_end_asics = dut.get_backend_asic_ids()

    asic_services = defaultdict(list)
    for service in dut.sonichost.DEFAULT_ASIC_SERVICES:
        # for multi ASIC randomly select one frontend ASIC
        # and one backend ASIC
        if dut.sonichost.is_multi_asic:
            asic_services[service] = []
            if len(front_end_asics):
                fe = random.choice(front_end_asics)
                asic_services[service].append(dut.get_docker_name(service, asic_index=fe))
            if len(back_end_asics):
                be = random.choice(back_end_asics)
                asic_services[service].append(dut.get_docker_name(service, asic_index=be))

    dut_info = {
        "intf_status": status,
        "features": features,
        "asic_services": asic_services,
    }

    if dut.sonichost.is_multi_asic:
        dut_info.update(
            {
                "frontend_asics": front_end_asics,
                "backend_asics": back_end_asics
            }
        )

    return dut_info

def test_update_testbed_metadata(duthosts, tbinfo, fanouthosts):
    metadata = {}
    tbname = tbinfo['conf-name']
    pytest_require(tbname, "skip test due to lack of testbed name.")

    for dut in duthosts:
        dutinfo = collect_dut_info(dut)
        metadata[dut.hostname] = dutinfo

    info = { tbname : metadata }
    folder = 'metadata'
    filepath = os.path.join(folder, tbname + '.json')
    try:
        if not os.path.exists(folder):
            os.mkdir(folder)
        with open(filepath, 'w') as yf:
            json.dump(info, yf, indent=4)
    except IOError as e:
        logger.warning('Unable to create file {}: {}'.format(filepath, e))

    prepare_autonegtest_params(duthosts, fanouthosts)


def test_disable_rsyslog_rate_limit(duthosts, enum_dut_hostname):
    duthost = duthosts[enum_dut_hostname]
    features_dict, succeed = duthost.get_feature_status()
    if not succeed:
        # Something unexpected happened.
        # We don't want to fail here because it's an util
        logging.warn("Failed to retrieve feature status")
        return
    for feature_name, state in features_dict.items():
        if 'enabled' not in state:
            continue
        duthost.modify_syslog_rate_limit(feature_name, rl_option='disable')


def collect_dut_lossless_prio(dut):
    config_facts = dut.config_facts(host=dut.hostname, source="running")['ansible_facts']

    if "PORT_QOS_MAP" not in config_facts.keys():
        return []

    port_qos_map = config_facts["PORT_QOS_MAP"]
    if len(port_qos_map.keys()) == 0:
        return []

    """ Here we assume all the ports have the same lossless priorities """
    intf = port_qos_map.keys()[0]
    if 'pfc_enable' not in port_qos_map[intf]:
        return []

    result = [int(x) for x in port_qos_map[intf]['pfc_enable'].split(',')]
    return result

def collect_dut_all_prio(dut):
    config_facts = dut.config_facts(host=dut.hostname, source="running")['ansible_facts']

    if "DSCP_TO_TC_MAP" not in config_facts.keys():
        return []

    dscp_to_tc_map_lists = config_facts["DSCP_TO_TC_MAP"]
    if len(dscp_to_tc_map_lists) != 1:
        return []

    profile = dscp_to_tc_map_lists.keys()[0]
    dscp_to_tc_map = dscp_to_tc_map_lists[profile]

    tc = [int(p) for p in dscp_to_tc_map.values()]
    return list(set(tc))

def collect_dut_lossy_prio(dut):
    lossless_prio = collect_dut_lossless_prio(dut)
    all_prio = collect_dut_all_prio(dut)
    return [p for p in all_prio if p not in lossless_prio]

def test_collect_testbed_prio(duthosts, tbinfo):
    all_prio = {}
    lossless_prio = {}
    lossy_prio = {}

    tbname = tbinfo['conf-name']
    pytest_require(tbname, "skip test due to lack of testbed name.")

    for dut in duthosts:
        all_prio[dut.hostname] = collect_dut_all_prio(dut)
        lossless_prio[dut.hostname] = collect_dut_lossless_prio(dut)
        lossy_prio[dut.hostname] = collect_dut_lossy_prio(dut)

    prio_info = [all_prio, lossless_prio, lossy_prio]
    file_names = [tbname + '-' + x + '.json' for x in ['all', 'lossless', 'lossy']]
    folder = 'priority'

    for i in range(len(file_names)):
        filepath = os.path.join(folder, file_names[i])
        try:
            if not os.path.exists(folder):
                os.mkdir(folder)
            with open(filepath, 'w') as yf:
                json.dump({ tbname : prio_info[i]}, yf, indent=4)
        except IOError as e:
            logger.warning('Unable to create file {}: {}'.format(filepath, e))

def test_update_saithrift_ptf(request, ptfhost):
    '''
    Install the correct python saithrift package on the ptf
    '''
    py_saithrift_url = request.config.getoption("--py_saithrift_url")
    if not py_saithrift_url:
        pytest.skip("No URL specified for python saithrift package")
    pkg_name = py_saithrift_url.split("/")[-1]
    ptfhost.shell("rm -f {}".format(pkg_name))
    result = ptfhost.get_url(url=py_saithrift_url, dest="/root", module_ignore_errors=True)
    if result["failed"] != False or "OK" not in result["msg"]:
        pytest.skip("Download failed/error while installing python saithrift package")
    ptfhost.shell("dpkg -i {}".format(os.path.join("/root", pkg_name)))
    logging.info("Python saithrift package installed successfully")


def test_stop_pfcwd(duthosts, enum_dut_hostname, tbinfo):
    '''
     Stop pfcwd on dual tor testbeds
    '''
    if 'dualtor' not in tbinfo['topo']['name']:
        pytest.skip("Skip this test on non dualTOR testbeds")

    dut = duthosts[enum_dut_hostname]
    dut.command('pfcwd stop')


def prepare_autonegtest_params(duthosts, fanouthosts):
    from tests.common.platform.device_utils import list_dut_fanout_connections

    cadidate_test_ports = {}

    for duthost in duthosts:
        all_ports = list_dut_fanout_connections(duthost, fanouthosts)

        cadidate_test_ports[duthost.hostname] = {}
        for dut_port, fanout, fanout_port in all_ports:
            auto_neg_mode = fanout.get_auto_negotiation_mode(fanout_port)
            if auto_neg_mode is not None:
                cadidate_test_ports[duthost.hostname][dut_port] = {'fanout':fanout.hostname, 'fanout_port': fanout_port}
    folder = 'metadata'
    filepath = os.path.join(folder, 'autoneg-test-params.json')
    try:
        with open(filepath, 'w') as yf:
            json.dump(cadidate_test_ports, yf, indent=4)
    except IOError as e:
        logger.warning('Unable to create a datafile for autoneg tests: {}. Err: {}'.format(filepath, e))


"""
    Separator for internal pretests.
    Please add public pretest above this comment and keep internal
    pretests below this comment.
"""
def test_conn_graph_valid(duthost, localhost):

    base_path = os.path.dirname(os.path.realpath(__file__))
    lab_conn_graph_path = os.path.join(base_path, "../ansible/files/")
    invs_need_test = ["str", "str2"]

    # inv_mapping file must exist and can be loaded
    inv_mapping_file = os.path.join(base_path, "../ansible/group_vars/all/inv_mapping.yml")
    if not os.path.exists(inv_mapping_file):
        pytest.fail("inv_mapping file doesn't exist")

    try:
        with open(inv_mapping_file) as fd:
            inv_map = yaml.load(fd, Loader=yaml.FullLoader)
    except:
        pytest.fail("Load inv_mapping file failed")

    # if inv_mapping file doesn't conatin invs_need_test, failed
    for inv_need_test in invs_need_test:
        if inv_need_test not in inv_map:
            pytest_fail("inv_mapping file doesn't conatin {}".format(inv_need_test))

    # Test connection graph if it can be loaded
    logger.info("Test connection graph for all of internal inventories: {}".format(invs_need_test))

    for inv_file in invs_need_test:
        lab_conn_graph_file = os.path.join(lab_conn_graph_path, inv_map[inv_file])
        kargs = {"filename": lab_conn_graph_file}
        conn_graph_facts = localhost.conn_graph_facts(
            **kargs)["ansible_facts"]
        if not conn_graph_facts:
            pytest.fail("build connection graph for {} failed.".format(inv_file))

def test_connect_to_internal_nameserver(duthosts, enum_dut_hostname):
    cmds = [
        "echo nameserver 10.64.5.5 > /etc/resolv.conf",
        "systemctl restart systemd-resolved"
    ]

    duthost = duthosts[enum_dut_hostname]
    duthost.shell_cmds(cmds=cmds)


def test_update_buffer_template(duthosts, enum_dut_hostname, localhost):
    '''
    Update the buffer templates to use internal cable len settings.
       1. Replace the default cable_len value to 300m.
       2. Update/add ports2cable mapping
    '''
    duthost = duthosts[enum_dut_hostname]
    pytest_require(not any(vers in duthost.os_version for vers in ["201811", "201911", "202012"]), "Skip updating templates for {}".format(duthost.os_version))

    hwsku = duthost.facts["hwsku"]
    platform = duthost.facts["platform"]
    path = os.path.join("/usr/share/sonic/device", "{}/{}".format(platform, hwsku))
    buffer_files = [ os.path.join(path, "buffers_defaults_t0.j2"),
                     os.path.join(path, "buffers_defaults_t1.j2")
                   ]
    update_results = update_cable_len(duthost, buffer_files)
    buf_temp_changed = False
    for item, result in zip(buffer_files, update_results):
        if result == "Found":
            buf_temp_changed = True
            path, orig_file = os.path.split(item)
            file_prefix = orig_file.split(".")[0]
            mod_file = "{}_new.j2".format(file_prefix)
            backup_file = os.path.join(path, "{}_orig.j2".format(file_prefix))
            duthost.shell("sudo mv {} {}".format(item, backup_file))
            duthost.copy(src=mod_file, dest=item)
            localhost.shell("sudo rm -f {}".format(mod_file))
            logging.info("Buffer template {} changed" .format(item))
        else:
            logging.info("Skip updating buffer template {}".format(item))
    if buf_temp_changed:
        logging.info("Executing load minigraph ...")
        config_reload(duthost, config_source='minigraph')
