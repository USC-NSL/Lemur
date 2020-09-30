"""
* The script implements an abstract deparser class. It parses egress
* header sequence, and unifies them to form a final deparser.
"""

import copy
import header

def convert_str_to_list(input_str):
	""" This function parses converts a list (in str format) to a real Python
	list, that has exactly the same set of elements as the original list.
	"""
	res_list = []
	s_index = input_str.index('[')
	e_index = input_str.index(']')
	list_content = input_str[(s_index+1):e_index]
	list_elements = list_content.split(',')
	for element in list_elements:
		res_list.append( element.strip() )

	return res_list


class mydeparser:
	"""
	This is the abstract deparser class. It can read and parse the
	P4 deparser in a P4 module.
	Args:
		all_headers: the global header list
		objects: the header parser tree
		deparser_seq: the final header sequence that works for every P4 module
		p4_code: the final generated P4 code.
	"""
	def __init__(self, input_header_list=[], input_deparser_seq=[]):
		self.all_headers = []
		self.objects = {}
		self.deparser_seq = []
		if len(input_header_list) >= 1:
			self.all_headers = copy.deepcopy(input_header_list)
		if len(input_deparser_seq) >= 1:
			self.deparser_seq = copy.deepcopy(input_deparser_seq)
		self.p4_code = ""
		return

	def read_deparser_rules(self, input_filename):
		hp = header.header_parser()
		hp.read_headers(input_filename)
		self.all_headers = hp.headers

		new_deparser_start = False
		with open(input_filename, 'r') as fp:
			line_count = 0
			for line in fp:
				line_count += 1
				line = line.strip()
				if line == '':
					continue
				if "Deparser" in line:
					new_deparser_start = True

				if not new_deparser_start:
					continue

				if '=' in line:
					if line.count('=') != 1:
						print "Exception: error defintion, line %d" %(line_count)
						return
					if '[' not in line and ']' not in line:
						continue
					mark_index = line.index('=')
					object_name = line[:mark_index].strip()
					object_definition = line[mark_index+1:].strip()
					object_obj = None
					object_obj = convert_str_to_list(object_definition)
					self.objects[object_name] = object_obj

				if "add deparser(" in line:
					deparser_seq_start = line.index('(')
					deparser_seq_end = line.index(')')
					deparser_seq_string = line[deparser_seq_start+1 : deparser_seq_end].strip()
		self.deparser_seq = self.objects[deparser_seq_string]
		return

	def generate_p4_code(self):
		res = ""
		res += "/*************************************************************************\n"
		res += "************************  D E P A R S E R  *******************************\n"
		res += "*************************************************************************/\n\n"
		res += "control MyDeparser(packet_out packet, in headers hdr) {\n"
		res += "\tapply {\n"

		for dp_header in reversed(self.deparser_seq):
			if dp_header in self.all_headers:
				res += "\tpacket.emit(hdr.%s);\n" %( dp_header.lower() )
		res += "\t}\n"
		res += "}\n"

		self.p4_code = res
		return


def my_deparser_tester():
	mdp = mydeparser()
	mdp.read_deparser_rules("design.dat")
	mdp.generate_p4_code()
	print mdp.p4_code

if __name__ == '__main__':
	my_deparser_tester()
