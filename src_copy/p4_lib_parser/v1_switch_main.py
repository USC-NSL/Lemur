
"""
* Title: v1_switch_main.py
* Description:
* The script is used to print the V1Switch(...) for the final P4 code file
* Currently, we do not parse anything for the V1Switch(...) module.
* (We might support more functions later)
* 
* Author: Jianfeng Wang
* Time: 01/18/2018
* Email: jianfenw@usc.edu
*
"""

class v1_switch_main:

	def __init__(self):
		self.p4_code = None
		self.my_parser_flg = True

		return

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
		return


def v1_switch_main_tester():

	switch_main = v1_switch_main()
	switch_main.generate_p4_code()
	print switch_main.p4_code


if __name__ == '__main__':

	v1_switch_main_tester()

