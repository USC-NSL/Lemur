
"""
* Title: my_checksum.py
* Description:
* The script is used to any checksum-related job, such as checksum verification
* and checksum updating.
* (We might support more functions later)
* 
* Author: Jianfeng Wang
* Time: 05/08/2018
* Email: jianfenw@usc.edu
*
"""


def compute_checksum_tester():
	csum = my_compute_checksum()
	csum.generate_p4_code()
	print csum.p4_code


if __name__ == '__main__':
	compute_checksum_tester()