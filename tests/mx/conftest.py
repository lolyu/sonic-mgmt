import pytest
import json
import os

from tests.common import config_reload

FILE_DIR = "mx/config"
CONFIG_FILE = "dhcp_server_vlan_conf.json"


def remove_all_vlans(cfg_facts, duthost):
    """
    Remove all vlans in DUT
    """
    if "VLAN_INTERFACE" in cfg_facts:
        vlan_intfs = cfg_facts["VLAN_INTERFACE"]
        for intf, prefixs in vlan_intfs.items():
            for prefix in prefixs.keys():
                duthost.remove_ip_from_port(intf, prefix)

    if "VLAN_MEMBER" in cfg_facts:
        vlan_members = cfg_facts["VLAN_MEMBER"]
        for vlan_name, members in vlan_members.items():
            vlan_id = int(''.join([i for i in vlan_name if i.isdigit()]))
            for member in members.keys():
                duthost.del_member_from_vlan(vlan_id, member)

            duthost.remove_vlan(vlan_id)


def create_vlan(duthost, vlan_config, dut_port_map):
    """
    Create vlans by vlan_config
    """
    intf_count = 0
    for vlan_id, config in vlan_config.items():
        duthost.shell("config vlan add {}".format(vlan_id))
        duthost.shell("config interface ip add Vlan{} {}".format(vlan_id, config["prefix"]))
        for member in config["members"]:
            duthost.add_member_to_vlan(vlan_id, dut_port_map[member], False)

            if len(config["members"]) != 1:
                intf_count += 1

    return intf_count


def remove_vlan(duthost, vlan_config, dut_port_map):
    """
    Remove vlan by vlan_config
    """
    for vlan_id, config in vlan_config.items():
        duthost.remove_ip_from_port("Vlan{}".format(vlan_id), config["prefix"])
        for member in config["members"]:
            duthost.del_member_from_vlan(vlan_id, dut_port_map[member])

        duthost.remove_vlan(vlan_id)


@pytest.fixture(scope="module")
def mx_common_setup_teardown(duthost, tbinfo):
    cfg_facts = duthost.config_facts(host=duthost.hostname, source="running")["ansible_facts"]
    remove_all_vlans(cfg_facts, duthost)

    # Get vlan configs
    cfg_facts = duthost.config_facts(host=duthost.hostname, source="running")["ansible_facts"]
    vlan_configs = json.load(open(os.path.join(FILE_DIR, CONFIG_FILE), "r"))

    dut_port_index = cfg_facts["port_index_map"]
    dut_index_port = dict(zip(dut_port_index.values(), dut_port_index.keys()))

    duts_map = tbinfo["duts_map"]
    dut_indx = duts_map[duthost.hostname]
    ptf_port_index = tbinfo["topo"]["ptf_map"][str(dut_indx)]
    ptf_index_port = dict(zip(ptf_port_index.values(), ptf_port_index.keys()))

    yield dut_index_port, ptf_index_port, vlan_configs

    config_reload(duthost)
