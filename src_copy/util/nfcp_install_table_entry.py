
"""
* 
* Title: nfcp_install_table_entry.py
* Description:
* This script provide a class to generate table entry files for testing.
* It also provides a function to automatically install all table entries into the switch.
*
"""

from __future__ import print_function
import sys
sys.path.append('..')
import os
import argparse
import subprocess
import collections
import copy
import math
from p4_lib_parser.ingress_match_action import p4_table
import connect as Conn


set_port_txt = "ucli\n\
pm\n\
port-add 21/0 100G RS\n\
port-add 27/0 100G RS\n\
port-enb 21/0\n\
port-enb 27/0\n\
an-set 21/0 1\n\
an-set 27/0 1\n\
end\n\n"

enter_pd_txt = "pd-"

ipv4_forward_entry = []
for chain_idx in range(1,4):
	ipv4_forward_entry += ['ipv4_dstAddr 1.0.%d.%d ipv4_dstAddr_prefix_length 32 action_dstAddr 0x123456123456 action_port 36' %(chain_idx, i) for i in range(3,13)]

class NFCP_entry_helper(object):

	def __init__(self, file_name, p4_node_list):
		self.base_dir = './test/entry/'
		self.entry_name = file_name
		self.entry_file_count = 0
		self.entry_files = []
		self.p4_nodes = copy.deepcopy(p4_node_list)
		return

	def NFCP_generate_table_entries(self):
		""" 
		Description: This function generatess all table entry files for testing purpose.
		Input/Output: None
		"""
		entry_file = '%s/%s_%d.txt' %(self.base_dir, self.entry_name, self.entry_file_count)
		fp = open(entry_file, 'w+')
		table_entry_list = [set_port_txt]

		# generate default_entries
		incoming_port = 36
		for p4_node in self.p4_nodes:
			spi, si = p4_node.service_path_id, p4_node.service_id
			if 'nshencap_%d_%d' %(spi, si) == p4_node.table_prefix:
				incoming_port = 168
				continue

			# process p4 nodes
			for table in p4_node.ingress_tables:
				#print(p4_node.table_prefix, table_name)
				table_name = '%s_%s' %(p4_node.table_prefix, table)
				table_str = p4_node.ingress_tables[table]
				if 'reads' not in table_str:
					continue
				table_obj = p4_table()
				table_obj.setup_from_str(table_str, p4_node)
				if table_obj.default_action:
					default_action = '%s_%s' %(p4_node.action_prefix, table_obj.default_action)
					set_default_action = 'pd %s set_default_action %s\n' %(table_name, default_action)
					table_entry_list.append(set_default_action)
				else:
					print('%s: %s' %(p4_node, table))

				# deal with IPv4
				if table=='ipv4_forward_table':
					for ipv4_entry in ipv4_forward_entry:
						forward_entry = 'pd %s add_entry ipv4forward_ipv4_forward_table_hit %s\n' %(table_name, ipv4_entry)
						table_entry_list.append(forward_entry)

				# deal with NAT
				if table=='interface_info_table':
					nat_interface_table = 'pd %s add_entry nat_set_if_info ig_intr_md_ingress_port %d action_ipv4_addr 1.0.1.3 action_mac_addr 0x12345612346 action_is_ext 1\n' \
						%(table_name, incoming_port)
					table_entry_list.append(nat_interface_table)
				if table=='nat':
					nat_table = 'pd %s add_entry nat_nat_hit_int_to_ext meta_is_ext_if 1 ipv4_valid 1 tcp_valid 1 ipv4_srcAddr 200.0.0.0 ipv4_srcAddr_mask 255.255.0.0 ipv4_dstAddr 0.0.0.0 ipv4_dstAddr_mask 0.0.0.0 tcp_srcPort 0 tcp_srcPort_mask 0 tcp_dstPort 0 tcp_dstPort_mask 0 priority 1 action_srcAddr 200.0.3.5 action_srcPort 80\n' \
						%(table_name)
					table_entry_list.append(nat_table)

				# deal with ACL
				if table=='acl_table':
					acl_table = 'pd %s add_entry acl_acl_table_hit ipv4_srcAddr 200.0.0.0 ipv4_srcAddr_mask 255.255.0.0 ipv4_dstAddr 0.0.0.0 ipv4_dstAddr_mask 0.0.0.0 tcp_srcPort 0 tcp_srcPort_mask 0 tcp_dstPort 0 tcp_dstPort_mask 0 priority 1\n' \
						%(table_name)
					table_entry_list.append(acl_table)

			incoming_port = 36


		table_entry_list.append('end\nexit\n')

		for line in table_entry_list:
			fp.write(line)
		fp.close()
		self.entry_files.append(entry_file)
		self.entry_file_count += 1
		return

	def NFCP_install_table_entries(self):
		""" 
		Description: This function installs all table entry files into the switch.
		Input/Output: None
		"""
		entry_file = '%s%s' %(self.base_dir, self.entry_name)
		print('Insert: %s' %(entry_file))
		Conn.NFCP_insert_table_entries(self.entry_name)
		return

def test_entry_helper():
	os.chdir('../')
	entry_file_name = raw_input('Input the entry file name: ')+'.txt'
	entry_helper = NFCP_entry_helper(entry_file_name, [])
	entry_helper.NFCP_install_table_entries()
	return

if __name__ == '__main__':
	test_entry_helper()

