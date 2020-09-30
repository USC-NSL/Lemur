"""
* The script outputs extra necessary code for the final P4 code file.
"""

class v1_switch_main:
	def __init__(self):
		self.p4_code = None
		self.my_parser_flg = True

	def generate_p4_code(self):
		res = ""
		res += "/*************************************************************************\n"
		res += "**************************   S W I T C H   *******************************\n"
		res += "*************************************************************************/\n\n"
		res += "V1Switch(\n"
		res += "MyParser(),\n"
		res += "MyVerifyChecksum(),\n"
		res += "MyIngress(),\n"
		res += "MyEgress(),\n"
		res += "MyComputeChecksum(),\n"
		res += "MyDeparser()\n"
		res += ")main;\n\n"
		self.p4_code = res

def v1_switch_main_tester():
	switch_main = v1_switch_main()
	switch_main.generate_p4_code()
	print switch_main.p4_code

if __name__ == '__main__':
	v1_switch_main_tester()
