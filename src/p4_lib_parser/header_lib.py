"""
* Title: header_lib.py
* Description:
* This file is the header library. 
* 'header.py' is looking at this file for these common libraries
*
* Author: Jianfeng Wang
* Time: 01/16/2018
* Email: jianfenw@usc.edu
*
"""

"""
Default data type:
In the following, we list all commonly used data types in P4 language.
These headers are always defined in the commonly used headers, i.e. IPv4, Ethernet
and so on.
"""
mac_addr_t = "macAddr_t"
ipv4_addr_t = "ip4Addr_t"
ipv6_addr_t = 'ip6Addr_t'
bit_128_t = "bit<128>"
bit_32_t = "bit<32>"
bit_24_t = "bit<24>"
bit_16_t = "bit<16>"
bit_13_t = "bit<13>"
bit_12_t = "bit<12>"
bit_10_t = "bit<10>"
bit_8_t = "bit<8>"
bit_6_t = "bit<6>"
bit_4_t = "bit<4>"
bit_3_t = "bit<3>"
bit_2_t = "bit<2>"
bit_1_t = "bit<1>"

class header_field(object):
	"""
	Description: the header_field class represents each header field in the 
	P4 header definition code. Each header_field instance = one fixed length
	header field.
	"""
	def __init__(self, field_name="", field_bits=-1, field_type=None):
		self.name = field_name
		self.bits = field_bits
		self.type = field_type

	def generate_p4_code(self):
		if self.type:
			res = "\t%s %s;\n" %(self.type, self.name)
		else:
			res = "\tbit<%d> %s;\n" %(self.bits, self.name)
		return res

	def generate_p414_code(self):
		res = "\t\t%s : %d;\n" %(self.name, self.bits)
		return res

"""
Default headers:
In the following, we list all commonly used headers for all NF modules.
"""
ethernet = [ header_field("dstAddr", 48, mac_addr_t), \
	header_field("srcAddr", 48, mac_addr_t), \
	header_field("etherType", 16) ]


ipv4 = [ header_field("version", 4), \
	header_field("ihl", 4), \
	header_field("diffserv", 8),\
	header_field("totalLen", 16),\
	header_field("identification", 16),\
	header_field("flags", 3),\
	header_field("fragOffset", 13),\
	header_field("ttl", 8),\
	header_field("protocol", 8),\
	header_field("hdrChecksum", 16),\
	header_field("srcAddr", 32, ipv4_addr_t),\
	header_field("dstAddr", 32, ipv4_addr_t) ]


ipv6 = [ header_field("version", 4), \
	header_field("traffic_class", 8),\
	header_field("flow_label", 20),\
	header_field("payload_len", 16),\
	header_field("next_hdr", 8),\
	header_field("hop_limit", 8),\
	header_field("srcAddr", 64, ipv6_addr_t),\
	header_field("dstAddr", 64, ipv6_addr_t) ]


tcp = [ header_field("srcPort", 16), \
	header_field("dstPort", 16), \
	header_field("seqNo", 32),\
	header_field("ackNo", 32),\
	header_field("dataOffset", 4),\
	header_field("res", 3),\
	header_field("ecn", 3),\
	header_field("ctrl", 6),\
	header_field("window", 16),\
	header_field("checksum", 16),\
	header_field("urgentPtr", 16)]

udp = [ header_field("srcPort", 16), \
	header_field("dstPort", 16), \
	header_field("hdr_length", 16),\
	header_field("checksum", 16)]

"""
header nsh {
    bit<2> version;
    bit<1> oBit;
    bit<1> uBit;
    bit<6> ttl;
    bit<6> totalLength;
    bit<4> unsign;
    bit<4> md;
    bit<8> nextProto;
    bit<24> spi;
    bit<8> si;
    bit<128> context;
}
"""

nsh = [ header_field("version", 2), \
	header_field("oBit", 1), \
	header_field("uBit", 1), \
	header_field("ttl", 6), \
	header_field("totalLength", 6), \
	header_field("unsign", 4), \
	header_field("md", 4), \
	header_field("nextProto", 8), \
	header_field("spi", 24), \
	header_field("si", 8), \
	header_field("context", 128)
]

arp = [ header_field("hw_addr", 16), \
    header_field("proto_addr", 16), \
    header_field("hw_addr_length", 8), \
    header_field("proto_addr_length", 8), \
    header_field("opcode", 16), \
    header_field("sender_hw_addr", 48, mac_addr_t), \
    header_field("sender_ip_addr", 32, ipv4_addr_t), \
    header_field("target_hw_addr", 48, mac_addr_t), \
    header_field("target_ip_addr", 32, ipv4_addr_t)
]

vlan = [ header_field("TCI", 16), \
    header_field("nextType", 16) \
]

vxlan = [ header_field("flag", 8), \
    header_field("reserve1", 24), \
    header_field("vni", 24), \
    header_field("reserve2", 8), \
]

all_header_list = {"ethernet":ethernet, \
	"ipv4":ipv4, \
	"ipv6":ipv6, \
	"tcp":tcp, \
	"udp":udp, \
	"nsh":nsh, \
    "arp":arp, \
    "vlan":vlan, \
    "vxlan":vxlan, \
	}
