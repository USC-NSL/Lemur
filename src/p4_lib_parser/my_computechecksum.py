"""
* The script implements an abstract my_compute_checksum class that
* generates the P4 code to generate a correct checksum.
"""


class my_compute_checksum:
	""" This class outputs the checksum computation code directly.
	"""
	def __init__(self):
		self.p4_code = None
		return

	def generate_p4_code(self):
		res = ""
		res += "/*************************************************************************\n"
		res += "**************   C H E C K S U M    C O M P U T A T I O N   **************\n"
		res += "*************************************************************************/\n\n"
		res += "control MyComputeChecksum(inout headers hdr, inout metadata meta) {\n"
		res += "\tapply {\n"
		res += "\t\tupdate_checksum(\n"
		res += "\t\t\thdr.ipv4.isValid(),\n"
		res += "\t\t\t{hdr.ipv4.version,\n"
		res += "\t\t\thdr.ipv4.ihl,\n"
		res += "\t\t\thdr.ipv4.diffserv,\n"
		res += "\t\thdr.ipv4.totalLen,\n"
		res += "\t\thdr.ipv4.identification,\n"
		res += "\t\thdr.ipv4.flags,\n"
		res += "\t\thdr.ipv4.fragOffset,\n"
		res += "\t\thdr.ipv4.ttl,\n"
		res += "\t\thdr.ipv4.protocol,\n"
		res += "\t\thdr.ipv4.srcAddr,\n"
		res += "\t\thdr.ipv4.dstAddr },\n"
		res += "\t\thdr.ipv4.hdrChecksum,\n"
		res += "\t\tHashAlgorithm.csum16);\n"
		res += "\t}\n"
		res += "}\n\n"
		self.p4_code = res

	def generate_p414_code(self):
		res = ""
		res += "/*************************************************************************\n"
		res += "**************   C H E C K S U M    C O M P U T A T I O N   **************\n"
		res += "*************************************************************************/\n\n"
		res += "field_list ipv4_field_list {\n"
		res += "\tipv4.version;\n"
		res += "\tipv4.ihl;\n"
		res += "\tipv4.diffserv;\n"
		res += "\tipv4.totalLen;\n"
		res += "\tipv4.identification;\n"
		res += "\tipv4.flags;\n"
		res += "\tipv4.fragOffset;\n"
		res += "\tipv4.ttl;\n"
		res += "\tipv4.protocol;\n"
		res += "\tipv4.srcAddr;\n"
		res += "\tipv4.dstAddr;\n"
		res += "}\n\n"

		res += 'field_list_calculation ipv4_chksum_calc {\n'
		res += '\tinput {\n'
		res += '\t\tipv4_field_list;\n'
		res += '\t}\n'
		res += '\talgorithm : csum16;\n'
		res += '\toutput_width: 16;\n'
		res += '}\n\n'

		res += 'calculated_field ipv4.hdrChecksum {\n'
		res += '\tupdate ipv4_chksum_calc;\n'
		res += '}\n'
		self.p4_code = res


def compute_checksum_tester():
	csum = my_compute_checksum()
	csum.generate_p4_code()
	print csum.p4_code

	csum.generate_p414_code()
	print csum.p4_code

if __name__ == '__main__':
	compute_checksum_tester()
