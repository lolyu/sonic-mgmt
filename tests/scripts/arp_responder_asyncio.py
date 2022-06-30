import argparse
import asyncio
import ctypes
import fcntl
import functools
import ipaddress
import json
import os.path
import signal
import socket
import struct
import sys

from scapy.all import Ether, Dot1Q, ARP, IPv6, ICMPv6ND_NS, ICMPv6ND_NA, ICMPv6NDOptDstLLAddr


# As defined in asm/socket.h
SO_ATTACH_FILTER = 26

# BPF filter "arp[6:2] = 1 || icmp6 && ip6[40] = 135"
arp_request_bpf_filter = [
    [0x28, 0, 0, 0x0000000c],
    [0x15, 9, 0, 0x00000806],
    [0x15, 0, 8, 0x000086dd],
    [0x30, 0, 0, 0x00000014],
    [0x15, 3, 0, 0x0000003a],
    [0x15, 0, 5, 0x0000002c],
    [0x30, 0, 0, 0x00000036],
    [0x15, 0, 3, 0x0000003a],
    [0x30, 0, 0, 0x00000036],
    [0x15, 0, 1, 0x00000087],
    [0x6, 0, 0, 0x00040000],
    [0x6, 0, 0, 0x00000000]
]


def bpf_stmt(code, jt, jf, k):
    """Format struct `sock_filter`."""
    return struct.pack("HBBI", code, jt, jf, k)


def build_bpfilter(filter):
    """Build BPF filter buffer."""
    return ctypes.create_string_buffer(b"".join(bpf_stmt(*_) for _ in filter))


def create_socket(interface):
    """Create a packet socket binding to a specified interface."""

    sock = socket.socket(family=socket.AF_PACKET, type=socket.SOCK_RAW, proto=0)

    sock.setblocking(False)
    bpf_filter = build_bpfilter(arp_request_bpf_filter)
    fprog = struct.pack("HL", len(arp_request_bpf_filter), ctypes.addressof(bpf_filter))
    sock.setsockopt(socket.SOL_SOCKET, SO_ATTACH_FILTER, fprog)

    sock.bind((interface, socket.SOCK_RAW))

    return sock


def get_mac(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    SIOCGIFHWADDR = 0x8927          # Get hardware address
    info = fcntl.ioctl(s.fileno(), SIOCGIFHWADDR,  struct.pack('256s', bytes(ifname, 'utf-8')[:15]))
    return ':'.join('%02x' % b for b in info[18:24])


class ARPResponderProtocol(asyncio.Protocol):
    """ARP responder protocol class to define read/write callbacks."""

    PADDING = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

    def __init__(self, on_con_lost, iface_config):
        self.transport = None
        self.on_con_lost = on_con_lost
        self.iface_config = iface_config
        self.vlan_id = self.iface_config.pop("vlan", None)
        self.arp_replies = []
        self.na_replies = []
        self._init_replies()

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        request = Ether(data)
        if ARP in request:
            if self._update_arp_replies(request):
                for reply in self.arp_replies:
                    self.transport.write(bytes(reply))
        elif IPv6 in request:
            if self._update_na_replies(request):
                for reply in self.na_replies:
                    self.transport.write(bytes(reply))

    def eof_received(self):
        return True

    def connection_lost(self, exc):
        if not self.on_con_lost.cancelled():
            self.on_con_lost.set_result(True)

    def _init_replies(self):
        for ip, mac in self.iface_config:
            if isinstance(ipaddress.ip_address(ip), ipaddress.IPv4Address):
                packet = Ether(src=mac)
                if self.vlan_id is not None:
                    packet /= Dot1Q(vlan=int(self.vlan_id))
                packet /= ARP(hwsrc=mac, psrc=ip, op=2)
                packet /= self.PADDING
                self.arp_replies.append(packet)
            else:
                packet = Ether(src=mac)
                if self.vlan_id is not None:
                    packet /= Dot1Q(vlan=int(self.vlan_id))
                packet /= IPv6(src=ip)
                packet /= ICMPv6ND_NA(R=0, S=1, O=1)
                packet /= ICMPv6NDOptDstLLAddr(lladdr=mac)
                self.na_replies.append(packet)

    def _update_arp_replies(self, request):
        requested_ip = request[ARP].pdst
        requested_mac = self.iface_config.get(requested_ip)
        if requested_mac is not None:
            for reply in self.arp_replies:
                reply[Ether].dst = request[Ether].src
                reply[Ether].src = requested_mac
                reply[ARP].hwdst = request[Ether].src
                reply[ARP].pdst = request[ARP].psrc
            return True
        return False

    def _update_na_replies(self, request):
        requested_ip = request[ICMPv6ND_NS].tgt
        requested_mac = self.iface_config.get(requested_ip)
        if requested_mac is not None:
            for reply in self.na_replies:
                reply[Ether].dst = request[Ether].src
                reply[Ether].src = requested_mac
                reply[IPv6].dst = request[IPv6].src
                reply[ICMPv6ND_NA].tgt = requested_ip
            return True
        return False


def stop_tasks(loop):
    """Stop all tasks in current event loop."""
    for task in asyncio.all_tasks(loop=loop):
        task.cancel()


async def arp_responder(iface, iface_config):
    """Start responding to ARP requests received on a specified interface."""
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    sock = create_socket(iface)
    transport, protocol = await loop._create_connection_transport(sock, lambda: ARPResponderProtocol(on_con_lost, iface_config), ssl=None, server_hostname=None)

    try:
        await protocol.on_con_lost
    finally:
        transport.close()
        sock.close()


async def start_arp_responders(ip_sets):
    """Start responding to ARP requests received from the interfaces."""
    responders = [arp_responder(iface, iface_config) for iface, iface_config in ip_sets.items()]

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, functools.partial(stop_tasks, loop))
    loop.add_signal_handler(signal.SIGTERM, functools.partial(stop_tasks, loop))

    await asyncio.gather(*responders, return_exceptions=True)


def parse_args():
    parser = argparse.ArgumentParser(description='ARP autoresponder')
    parser.add_argument('--conf', '-c', type=str, dest='conf', default='/tmp/from_t1.json', help='path to json file with configuration')
    parser.add_argument('--extended', '-e', action='store_true', dest='extended', default=False, help='enable extended mode')
    args = parser.parse_args()

    return args


def parse_config(config_file, is_extended):
    """Parse config file to get IP/MAC mappings."""
    ip_sets = {}
    with open(config_file) as fd:
        data = json.load(fd)

        for iface, ip_dict in data.items():
            if "@" in iface:
                iface, vlan_id = iface.split("@")
                ip_sets[iface] = {"vlan": vlan_id}
            else:
                ip_sets[iface] = {}

            if is_extended:
                for ip, mac in ip_dict.items():
                    ip_sets[iface][ip] = mac
            else:
                for ip in ip_dict:
                    ip_sets[iface][ip] = get_mac(iface)
    return ip_sets


if __name__ == "__main__":
    args = parse_args()

    if not os.path.exists(args.conf):
        print(f"Can't find file {args.conf}", file=sys.stderr)
        sys.exit(1)

    ip_sets = parse_config(args.conf, args.extended)
