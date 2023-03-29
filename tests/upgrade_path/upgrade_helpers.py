import pytest
import logging
import time
import tempfile
import random
import ipaddress
from six.moves.urllib.parse import urlparse
from tests.common.helpers.assertions import pytest_assert
from tests.common import reboot
from tests.common.reboot import get_reboot_cause, reboot_ctrl_dict
from tests.common.reboot import REBOOT_TYPE_WARM

# internal only import - used by ferret functions
import json
import os

logger = logging.getLogger(__name__)

TMP_VLAN_PORTCHANNEL_FILE = '/tmp/portchannel_interfaces.json'
TMP_VLAN_FILE = '/tmp/vlan_interfaces.json'
TMP_PORTS_FILE = '/tmp/ports.json'
TMP_PEER_INFO_FILE = "/tmp/peer_dev_info.json"
TMP_PEER_PORT_INFO_FILE = "/tmp/neigh_port_info.json"


def pytest_runtest_setup(item):
    from_list = item.config.getoption('base_image_list')
    to_list = item.config.getoption('target_image_list')
    if not from_list or not to_list:
        pytest.skip("base_image_list or target_image_list is empty")


@pytest.fixture(scope="module")
def restore_image(localhost, duthosts, rand_one_dut_hostname, upgrade_path_lists, tbinfo):
    _, _, _, restore_to_image = upgrade_path_lists
    yield
    duthost = duthosts[rand_one_dut_hostname]
    if restore_to_image:
        logger.info("Preparing to cleanup and restore to {}".format(restore_to_image))
        # restore orignial image
        install_sonic(duthost, restore_to_image, tbinfo)
        # Perform a cold reboot
        reboot(duthost, localhost)


def get_reboot_command(duthost, upgrade_type):
    reboot_command = reboot_ctrl_dict.get(upgrade_type).get("command")
    if upgrade_type == REBOOT_TYPE_WARM:
        next_os_version = duthost.shell('sonic_installer list | grep Next | cut -f2 -d " "')['stdout']
        current_os_version = duthost.shell('sonic_installer list | grep Current | cut -f2 -d " "')['stdout']
        # warm-reboot has to be forced for an upgrade from 201811 to 201811+ to bypass ASIC config changed error
        if 'SONiC-OS-201811' in current_os_version and 'SONiC-OS-201811' not in next_os_version:
            reboot_command = "warm-reboot -f"
    return reboot_command


def check_sonic_version(duthost, target_version):
    current_version = duthost.image_facts()['ansible_facts']['ansible_image_facts']['current']
    assert current_version == target_version, \
        "Upgrade sonic failed: target={} current={}".format(target_version, current_version)


def install_sonic(duthost, image_url, tbinfo):
    new_route_added = False
    if urlparse(image_url).scheme in ('http', 'https',):
        mg_gwaddr = duthost.get_extended_minigraph_facts(tbinfo).get("minigraph_mgmt_interface", {}).get("gwaddr")
        mg_gwaddr = ipaddress.IPv4Address(mg_gwaddr)
        rtinfo_v4 = duthost.get_ip_route_info(ipaddress.ip_network('0.0.0.0/0'))
        for nexthop in rtinfo_v4['nexthops']:
            if mg_gwaddr == nexthop[0]:
                break
        else:
            # Temporarily change the default route to mgmt-gateway address. This is done so that
            # DUT can download an image from a remote host over the mgmt network.
            logger.info("Add default mgmt-gateway-route to the device via {}".format(mg_gwaddr))
            duthost.shell("ip route replace default via {}".format(mg_gwaddr), module_ignore_errors=True)
            new_route_added = True
        res = duthost.reduce_and_add_sonic_images(new_image_url=image_url)
    else:
        out = duthost.command("df -BM --output=avail /host",
                        module_ignore_errors=True)["stdout"]
        avail = int(out.split('\n')[1][:-1])
        if avail >= 2000:
            # There is enough space to install directly
            save_as = "/host/downloaded-sonic-image"
        else:
            save_as = "/tmp/tmpfs/downloaded-sonic-image"
            # Create a tmpfs partition to download image to install
            duthost.shell("mkdir -p /tmp/tmpfs", module_ignore_errors=True)
            duthost.shell("umount /tmp/tmpfs", module_ignore_errors=True)
            duthost.shell("mount -t tmpfs -o size=1300M tmpfs /tmp/tmpfs", module_ignore_errors=True)
        logger.info("Image exists locally. Copying the image {} into the device path {}".format(image_url, save_as))
        duthost.copy(src=image_url, dest=save_as)
        res = duthost.reduce_and_add_sonic_images(save_as=save_as)

    # if the new default mgmt-gateway route was added, remove it. This is done so that
    # default route src address matches Loopback0 address
    if new_route_added:
        logger.info("Remove default mgmt-gateway-route earlier added")
        duthost.shell("ip route del default via {}".format(mg_gwaddr), module_ignore_errors=True)
    return res['ansible_facts']['downloaded_image_version']


def check_services(duthost):
    """
    Perform a health check of services
    """
    logging.info("Wait until DUT uptime reaches {}s".format(300))
    while duthost.get_uptime().total_seconds() < 300:
            time.sleep(1)
    logging.info("Wait until all critical services are fully started")
    logging.info("Check critical service status")
    pytest_assert(duthost.critical_services_fully_started(), "dut.critical_services_fully_started is False")

    for service in duthost.critical_services:
        status = duthost.get_service_props(service)
        pytest_assert(status["ActiveState"] == "active", "ActiveState of {} is {}, expected: active".format(service, status["ActiveState"]))
        pytest_assert(status["SubState"] == "running", "SubState of {} is {}, expected: running".format(service, status["SubState"]))


def check_reboot_cause(duthost, expected_cause):
    reboot_cause = get_reboot_cause(duthost)
    logging.info("Checking cause from dut {} to expected {}".format(reboot_cause, expected_cause))
    return reboot_cause == expected_cause


@pytest.fixture
def create_hole_in_tcam(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    ROUTER_MAC_ADDRESS = duthost.shell(
        "sonic-cfggen -d -v \'DEVICE_METADATA.localhost.mac\'")["stdout_lines"][0].decode("utf-8")
    DOWNSTREAM_VLAN_LIST = duthost.shell(
        "sonic-cfggen -d -v 'VLAN|list' | tr -d '[],'")['stdout']
    VLAN = duthost.shell(
        "echo {} | sed -e 's/'u/'/'".format(DOWNSTREAM_VLAN_LIST))['stdout']
    APP_DB_FDB_ROUTER_MAC = ROUTER_MAC_ADDRESS.upper().replace(':', '-')
    STATE_DB_FDB_ROUTER_MAC = duthost.shell("echo {}".format(ROUTER_MAC_ADDRESS))['stdout']
    BRCM_STATION_ROUTER_MAC = ROUTER_MAC_ADDRESS.upper().replace(':', '')

    def apply_fdb_config(duthost, vlan_id, iface, appdb_router_mac):
        """ Creates FDB config and applies it on DUT """
        dut_fdb_config = os.path.join("/tmp", "fdb.json")
        fdb_entry_json = [{ "FDB_TABLE:{}:{}".format(vlan_id, appdb_router_mac):
            { "port": iface, "type": "dynamic" }, "OP": "SET" }]
        with tempfile.NamedTemporaryFile(suffix=".json", prefix="fdb_config") as fp:
            logger.info("Generating FDB config")
            json.dump(fdb_entry_json, fp)
            fp.flush()
            # Copy FDB JSON config to switch
            duthost.template(src=fp.name, dest=dut_fdb_config, force=True)
        # Copy FDB JSON config to SWSS container
        cmd = "docker cp {} swss:/".format(dut_fdb_config)
        duthost.command(cmd)
        # Add FDB entry
        cmd = "docker exec -i swss swssconfig /fdb.json"
        duthost.command(cmd)

    def create_hole(duthost, localhost, metadata_process):
        PORT = random.choice(duthost.get_vlan_intfs())
        # Add router MAC to state-db
        duthost.shell(
            "redis-cli -n 6 hset 'FDB_TABLE|'Vlan1000:'{}'  'type' 'dynamic'".format(STATE_DB_FDB_ROUTER_MAC))
        duthost.shell(
            "redis-cli -n 6 hset 'FDB_TABLE|'Vlan1000:'{}'  'port' {}".format(STATE_DB_FDB_ROUTER_MAC, PORT))

        # Add router MAC to app-db
        apply_fdb_config(duthost, VLAN, PORT, APP_DB_FDB_ROUTER_MAC)
        # Check if the router mac exists in the DBs
        exists_in_statedb = duthost.shell(
            "redis-cli -n 6 EXISTS 'FDB_TABLE|'{}':'{}".format(VLAN, STATE_DB_FDB_ROUTER_MAC))['stdout']
        exists_in_appdb = duthost.shell(
            "redis-cli -n 0 EXISTS 'FDB_TABLE:'{}':'{}".format(VLAN, APP_DB_FDB_ROUTER_MAC))['stdout']
        if exists_in_statedb != '1' or exists_in_appdb != '1':
            logger.error("Failed to add router MAC address to db. Statedb - {}; APPLdb - {}".format(
                exists_in_statedb, exists_in_appdb))

        # Warm reboot to create a hole in my_station_tcam
        reboot(duthost, localhost, reboot_type=REBOOT_TYPE_WARM)

        # Verify that the tcam hole is now created
        STATION_TCAM_SIZE = duthost.shell(
            "bcmcmd -n 0 'listmem my_station_tcam' | grep 'Entries:' | awk '{print $2}'")['stdout']
        STATION_TCAM_LAST_INDEX_EXIST= duthost.shell(
            "bcmcmd -n 0 'dump chg my_station_tcam' | grep -c '\[{}\]'".format(
                int(STATION_TCAM_SIZE) - 1))['stdout']
        if STATION_TCAM_LAST_INDEX_EXIST == '1':
            logger.info("Hole in TCAM found")
        else:
            logger.error("Hole in TCAM not found when expected.")

        # If Metadata script is used, the below steps will be performed by the replaced script on the device
        if not metadata_process:
            logger.info("Set up Station TCAM Entry 1 Vlan Mask as 0 for mitigation on Broadcom")
            duthost.shell("bcmcmd 'l2 station add id=1 mac=0x{} macm=0xffffffffffff ".format(BRCM_STATION_ROUTER_MAC) +
            "vlanid=0 vlanidm=0 ipv4=1 ipv6=1 arprarp=1 replace=1'")
            # Remove app db entry before warmboot to image with a fix
            duthost.shell("redis-cli -n 0 del 'FDB_TABLE:'{}':'{}".format(VLAN, APP_DB_FDB_ROUTER_MAC))

    yield create_hole

    # clean up
    duthost.shell("redis-cli -n 6 del 'FDB_TABLE|'{}':'{}".format(VLAN, STATE_DB_FDB_ROUTER_MAC), module_ignore_errors=True)
    duthost.shell("redis-cli -n 0 del 'FDB_TABLE:'{}':'{}".format(VLAN, APP_DB_FDB_ROUTER_MAC), module_ignore_errors=True)
    duthost.shell("docker exec -i swss rm /fdb.json*", module_ignore_errors=True)


def setup_ferret(duthost, ptfhost, tbinfo):
    '''
        Sets Ferret service on PTF host.
    '''
    VXLAN_CONFIG_FILE = '/tmp/vxlan_decap.json'
    def prepareVxlanConfigData(duthost, ptfhost, tbinfo):
        '''
            Prepares Vxlan Configuration data for Ferret service running on PTF host

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)
                ptfhost (AnsibleHost): Packet Test Framework (PTF)

            Returns:
                None
        '''
        mgFacts = duthost.get_extended_minigraph_facts(tbinfo)
        vxlanConfigData = {
            'minigraph_port_indices': mgFacts['minigraph_ptf_indices'],
            'minigraph_portchannel_interfaces': mgFacts['minigraph_portchannel_interfaces'],
            'minigraph_portchannels': mgFacts['minigraph_portchannels'],
            'minigraph_lo_interfaces': mgFacts['minigraph_lo_interfaces'],
            'minigraph_vlans': mgFacts['minigraph_vlans'],
            'minigraph_vlan_interfaces': mgFacts['minigraph_vlan_interfaces'],
            'dut_mac': duthost.facts['router_mac']
        }
        with open(VXLAN_CONFIG_FILE, 'w') as file:
            file.write(json.dumps(vxlanConfigData, indent=4))

        logger.info('Copying ferret config file to {0}'.format(ptfhost.hostname))
        ptfhost.copy(src=VXLAN_CONFIG_FILE, dest='/tmp/')

    ptfhost.copy(src="arp/files/ferret.py", dest="/opt")
    result = duthost.shell(
        cmd='''ip route show type unicast |
        sed -e '/proto 186\|proto zebra\|proto bgp/!d' -e '/default/d' -ne '/0\//p' |
        head -n 1 |
        sed -ne 's/0\/.*$/1/p'
        '''
    )

    pytest_assert(len(result['stdout'].strip()) > 0, 'Empty DIP returned')

    dip = result['stdout']
    logger.info('VxLan Sender {0}'.format(dip))

    vxlan_port_out = duthost.shell('redis-cli -n 0 hget "SWITCH_TABLE:switch" "vxlan_port"')
    if 'stdout' in vxlan_port_out and vxlan_port_out['stdout'].isdigit():
        vxlan_port = int(vxlan_port_out['stdout'])
        ferret_args = '-f /tmp/vxlan_decap.json -s {0} -a {1} -p {2}'.format(
            dip, duthost.facts["asic_type"], vxlan_port)
    else:
        ferret_args = '-f /tmp/vxlan_decap.json -s {0} -a {1}'.format(dip, duthost.facts["asic_type"])

    ptfhost.host.options['variable_manager'].extra_vars.update({'ferret_args': ferret_args})

    logger.info('Copying ferret config file to {0}'.format(ptfhost.hostname))
    ptfhost.template(src='arp/files/ferret.conf.j2', dest='/etc/supervisor/conf.d/ferret.conf')

    logger.info('Generate pem and key files for ssl')
    ptfhost.command(
        cmd='''openssl req -new -x509 -keyout test.key -out test.pem -days 365 -nodes
        -subj "/C=10/ST=Test/L=Test/O=Test/OU=Test/CN=test.com"''',
        chdir='/opt'
    )

    prepareVxlanConfigData(duthost, ptfhost, tbinfo)

    logger.info('Refreshing supervisor control with ferret configuration')
    ptfhost.shell('supervisorctl reread && supervisorctl update')
    ptfhost.shell('supervisorctl restart ferret')
