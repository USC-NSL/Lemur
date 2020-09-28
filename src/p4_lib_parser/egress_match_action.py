
"""
* Title: egress_match_action.py
* Description:
* The script is used to parse the egress actions/tables specification part 
* in the target file.
* In order to handle conflicts, the output code should contain a prefix.
* The prefix is the library file's name.
*
* Author: Jianfeng Wang
* Time: 01/23/2018
* Email: jianfenw@usc.edu
"""

p414_egress_empty = 'control egress {\n}\n'

p416_egress_head = "control MyEgress(inout headers hdr,\n\
\tinout metadata meta,\n\
\tinout standard_metadata_t standard_metadata) {\n"


class egress_match_action:

	def __init__(self):

		self.output_prefix = ""

		self.p4_code = None
		self.p4_action_code = None
		self.p4_table_code = None
		self.p4_apply_code = None
		return

	def read_default_prefix(self, filename):
		with open(filename, 'r') as fp:
			line_count = 0
			for line in fp:
				line_count += 1

				if '=' in line:
					if line.count('=') != 1:
						print "Exception: error definition, line %d" %(line_count)
						return
					mark_index = line.index('=')
					object_name = line[:mark_index].strip()
					if object_name == "default_prefix":
						#print object_name, line[mark_index+1:].strip(), \
						#	extract_keyword_from_string(line[mark_index+1:].strip(), '"' )
						self.output_prefix = extract_keyword_from_string(line[mark_index+1:].strip(),'"')
		return

	def generate_p4_code(self):

		res = ""
		self.generate_p4_action_code()
		self.generate_p4_table_code()
		self.generate_p4_apply_code()
		res += self.p4_action_code
		res += self.p4_table_code
		res += self.p4_apply_code

		self.p4_code = res
		self.generate_p4_default_code()
		return

	def generate_p414_code(self):
		self.p4_code = p414_egress_empty
		return

	def generate_p4_action_code(self):
		self.p4_action_code = ""
		return

	def generate_p4_table_code(self):
		self.p4_table_code = ""
		return

	def generate_p4_apply_code(self):
		self.p4_apply_code = ""
		self.p4_apply_code += "\n\tapply{\n"
		self.p4_apply_code += "\t}\n"
		return

	def generate_p4_default_code(self):
		"""
		This function is used to generate the default header code and tail code
		for the EGRESS part.
		"""
		self.p4_code = p416_egress_head + self.p4_code
		self.p4_code += "}\n"
		return


def my_egress_tester():

	egress = egress_match_action()
	egress.generate_p4_code()
	print egress.p4_code
	return

if __name__ == '__main__':

	my_egress_tester()

