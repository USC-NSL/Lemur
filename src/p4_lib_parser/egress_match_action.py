"""
* The script implements an abstract egress_match_action class that
* parses the egress action/table specification part in a Lemur P4
* module.
* To handle conflicts of naming, the code generator must add a prefix
* the each match/action tables defined by a P4 module.
"""

# The default egress code that is placed at the head and tail of an
# egress pipeline code section.
p414_egress_empty = 'control egress {\n}\n'
p416_egress_head = "control MyEgress(inout headers hdr,\n\
\tinout metadata meta,\n\
\tinout standard_metadata_t standard_metadata) {\n"


class egress_match_action:
	"""
	This is the abstract egress match/action class. It can read and
	parse actions, tables, and the pipeline in the egress section of
	a P4 module.
	Args:
		output_prefix: the prefix added to actions and tables, type(str)
		p4_code: the final generated P4 code
		p4_action_code: the final generated P4 action code
		p4_table_code: the final generated P4 table code
		p4_apply_code: the final generated P4 pipeline code
		Note: p4_code = p4_action_code + p4_table_code + p4_apply_code
	"""
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

	def generate_p414_code(self):
		self.p4_code = p414_egress_empty

	def generate_p4_action_code(self):
		self.p4_action_code = ""

	def generate_p4_table_code(self):
		self.p4_table_code = ""

	def generate_p4_apply_code(self):
		self.p4_apply_code = ""
		self.p4_apply_code += "\n\tapply{\n"
		self.p4_apply_code += "\t}\n"

	def generate_p4_default_code(self):
		"""
		This function generates extra comments at the head and tail of
		the egress section. This is to separate the egress code from
		other pieces.
		"""
		self.p4_code = p416_egress_head + self.p4_code
		self.p4_code += "}\n"


def my_egress_tester():
	egress = egress_match_action()
	egress.generate_p4_code()
	print egress.p4_code
	return

if __name__ == '__main__':
	my_egress_tester()
