"""
Remote platform

This platform uses physical ethernet interfaces.
"""
import os
import yaml


ETH_PFX = 'eth'
BACKPLANE = 'backplane'
SUB_INTF_SEP = '.'


def get_ifaces():
    with open('/proc/net/dev') as fp:
        all = fp.read()

    ifaces = []
    for line in all.split('\n'):
        # Skip a header
        if ':' not in line:
            continue

        iface = line.split(':')[0].strip()

        # Skip not FP interfaces and vlan interface, like eth1.20
        if ETH_PFX not in iface and BACKPLANE != iface:
            continue

        ifaces.append(iface)

    # Sort before return
    return ifaces


def build_ifaces_map(ifaces, ptf_config=None):
    """Build interface map for ptf to init dataplane."""
    ptf_port_mapping_mode = "use_orig_interface"
    constants_file = os.path.join(os.path.dirname(__file__), "constants.yaml")
    if os.path.exists(constants_file):
        with open(constants_file) as fd:
            constants = yaml.safe_load(fd)
            ptf_port_mapping_mode = constants.get(
                "PTF_PORT_MAPPING_MODE", ptf_port_mapping_mode)

    need_backplane = False
    if ptf_config is not None and 'need_backplane' in ptf_config:
        need_backplane = ptf_config['need_backplane']

    sub_ifaces = []
    iface_map = {}
    used_index = set()
    backplane_exist = False
    for iface in ifaces:
        iface_suffix = iface.lstrip(ETH_PFX)
        if SUB_INTF_SEP in iface_suffix:
            iface_index = int(iface_suffix.split(SUB_INTF_SEP)[0])
            sub_ifaces.append((iface_index, iface))
        elif iface == BACKPLANE:
            backplane_exist = True
        else:
            iface_index = int(iface_suffix)
            iface_map[(0, iface_index)] = iface
            used_index.add(iface_index)

    count = 1
    while count in used_index:
        count = count + 1
    if backplane_exist and need_backplane:
        iface_map[(0, count)] = "backplane"

    if ptf_port_mapping_mode == "use_sub_interface":
        # override those interfaces that has sub interfaces
        for i, si in sub_ifaces:
            iface_map[(0, i)] = si
        return iface_map
    elif ptf_port_mapping_mode == "use_orig_interface":
        return iface_map
    else:
        raise ValueError("Unsupported ptf port mapping mode: %s" %
                         ptf_port_mapping_mode)


def platform_config_update(config):
    """
    Update configuration for the remote platform

    @param config The configuration dictionary to use/update
    """

    remote_port_map = build_ifaces_map(get_ifaces(), config)
    config["port_map"] = remote_port_map.copy()
    config["caps_table_idx"] = 0
