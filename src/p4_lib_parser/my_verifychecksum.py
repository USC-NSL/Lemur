
"""
* Title: my_verifychecksum.py
* Description:
* The script is used to print the MyCheckSum(...) for the final P4 code file
* Currently, we do not parse anything for the MyCheckSum(...) module
* (We might support more functions later)
*
* Author: Jianfeng Wang
* Time: 01/26/2018
* Email: jianfenw@usc.edu
*
"""


class my_verify_checksum:

	def __init__(self):
		self.p4_code = None
		return

	def generate_p4_code(self):
		res = ""

		res += "/*************************************************************************\n"
		res += "*************   C H E C K S U M    V E R I F I C A T I O N   *************\n"
		res += "*************************************************************************/\n\n"

		res += "control MyVerifyChecksum(inout headers hdr, inout metadata meta) {\n"
		res += "\tapply { }\n"
		res += "}\n"

		self.p4_code = res
		return


def verify_checksum_tester():
	my_cksum = my_verify_checksum()
	my_cksum.generate_p4_code()
	print my_cksum.p4_code


if __name__ == '__main__':
	verify_checksum_tester()


