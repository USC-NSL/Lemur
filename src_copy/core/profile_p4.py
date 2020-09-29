
"""
* 
* Title: profile_p4.py
* Description:
* This script is a corase estimation for the P4 stage usage.
*
"""
from __future__ import print_function
import sys
sys.path.append('..')
import os
import subprocess
import collections
import copy
import math
from p4_lib_parser.ingress_match_action import p4_table
import nfcp_library_parser as libParser
import nfcp_code_generator as codeGen
import connect as Conn
import p4_lib_parser.header as header
import p4_lib_parser.header_lib as header_lib
import util.lang_parser_helper as lang_helper
from util.nfcp_nf_node import nf_chain_graph, nf_node

global tcam_usage_dict, sram_usage_dict
global TCAM_BLOCK_WIDTH, TCAM_BLOCK_DEPTH
global SRAM_BLOCK_WIDTH, SRAM_BLOCK_DEPTH
global TCAM_BLOCK_PER_STAGE, SRAM_BLOCK_PER_STAGE

TCAM_BLOCK_WIDTH, TCAM_BLOCK_DEPTH = 44.0, 512.0
SRAM_BLOCK_WIDTH, SRAM_BLOCK_DEPTH = 80.0, 2000.0
TCAM_BLOCK_PER_STAGE = 24.0
SRAM_BLOCK_PER_STAGE = 80.0

tcam_usage_dict = {'sys_init_metadata_apply': 1, \
		'sys_remove_nsh_header_apply': 1, \
		'spi_select_table': 1, \
		'sys_send_to_controller_apply': 1, \
		'sys_drop_apply': 1, \
		'sys_valid_nsh_header_apply': 1, \
		'sys_handle_next_proto_vlan_apply': 1, \
		'sys_send_to_bess_apply': 1, \
		'sys_handle_next_proto_ipv4_apply': 1}

sram_usage_dict = {'sys_init_metadata_apply': 1, \
		'sys_remove_nsh_header_apply': 1, \
		'spi_select_table': 1, \
		'sys_send_to_controller_apply': 1, \
		'sys_drop_apply': 1, \
		'sys_valid_nsh_header_apply': 1, \
		'sys_handle_next_proto_vlan_apply': 1, \
		'sys_send_to_bess_apply': 1, \
		'sys_handle_next_proto_ipv4_apply': 1}


class p4_usage_checker(object):
	def __init__(self, p4_file_name, p4_list, MAX_STAGE_NUM):
		self.p4_list = copy.deepcopy(p4_list)
		self.MAX_STAGE_NUM = MAX_STAGE_NUM
		self.base_path = os.getcwd()
		self.stage_usage = 0

		if p4_file_name:
			Conn.NFCP_check_logical_table(p4_file_name)
		return

	def NFCP_check_p4_stage_usage(self):
		# update stage usage for each p4 tables
		self.NFCP_update_p4_usage()
		cwd = os.getcwd()
		log_file = './core/table_dependengency_group.log'
		table_groups = self.NFCP_read_graph_log(log_file)
		self.stage_usage = self.NFCP_get_p4_stage_usage(table_groups)
		if self.stage_usage > self.MAX_STAGE_NUM:
			return False
		else:
			return True

	def NFCP_update_p4_usage(self):
		"""
		Description: This function updates the TCAM / SRAM usage for each table in the
		given P4 node list. The P4 list is for one placement decision.
		Input: p4_list (type=List)
		Output: None
		"""
		lib_combine = codeGen.nfcp_code_generator(None, self.p4_list, 'p414')
		lib_combine.lib_combine_main()
		field_to_bit = {}
		for header in lib_combine.header_list:
			hd = header.lower()
			field_to_bit[hd] = 1
			for field in header_lib.all_header_list[hd]:
				field_to_bit['%s.%s' %(hd, field.name)] = field.bits
		for meta, val in lib_combine.metadata_dict.items():
			field_to_bit['meta.%s' %(meta)] = int(val)
		# if you found extra header field, please add it here
		field_to_bit['ig_intr_md.ingress_port'] = 13

		for i, node in enumerate(self.p4_list):
			for table in node.ingress_tables:
				if i==0:
					table_name = '%s_%s' %(node.action_prefix, table)
				else:
					table_name = '%s_%s' %(node.table_prefix, table)
				self.NFCP_update_p4_usage_helper(table_name, node.ingress_tables[table], node, field_to_bit)
		#print(tcam_usage_dict, sram_usage_dict)
		return

	def NFCP_update_p4_usage_helper(self, table_name, table_str, p4_node, field_to_bit):
		"""
		Description: The helper function updates the TCAM/SRAM usage for each table.
		Input: table_name (type=Str), table_str (type=Str)
		Output: None
		"""
		global tcam_usage_dict, sram_usage_dict
		p4_table_obj = p4_table()
		p4_table_obj.setup_from_str(table_str, p4_node)
		
		if table_name not in sram_usage_dict:
			sram_usage_dict[table_name] = 0.0
		if table_name not in tcam_usage_dict:
			tcam_usage_dict[table_name] = 0.0
		
		# match: header or metadata field (p4_node must see these fields)
		for key, val in p4_table_obj.key_set.items():
			field_width = 1
			if key in field_to_bit:
				field_width = field_to_bit[key]
			else:
				raise "Error: unrecongnized matching field"
			if val == 'exact': # update SRAM
				sram_usage_dict[table_name] += math.ceil((field_width/ SRAM_BLOCK_WIDTH)) * \
					math.ceil((p4_table_obj.table_size / SRAM_BLOCK_DEPTH))
			elif val == 'ternary': # update TCAM
				tcam_usage_dict[table_name] += math.ceil((field_width/ TCAM_BLOCK_WIDTH)) * \
					math.ceil((p4_table_obj.table_size / TCAM_BLOCK_DEPTH))
			elif val == 'lpm':
				sram_usage_dict[table_name] += math.ceil((field_width/ SRAM_BLOCK_WIDTH)) * \
					math.ceil((p4_table_obj.table_size / SRAM_BLOCK_DEPTH))
		
		# Uncomment this line to print stage usage
		#print('Table %s: tcam-%d, sram-%d' %(table_name, tcam_usage_dict[table_name], sram_usage_dict[table_name]))
		return

	def NFCP_read_graph_log(self, log_file):
		"""
		Description: This function reads the log_file. It parses the table dependency grouup.
		Input: log_file (type=Str)
		Output: table_groups (type=List)
		"""
		f = open(log_file, 'r')
		# read in table dependency information
		table_groups = []
		for line in f:
			table_group = lang_helper.convert_str_to_list(line)
			if len(table_group) > 0:
				for i, table in enumerate(table_group):
					table_group[i] = table.strip()[1:-1]
				table_groups.append(table_group)
		f.close()
		return table_groups

	def NFCP_get_p4_stage_usage(self, table_groups):
		"""
		Description: This function analyzes each table group in the table group list.
		It should sum through all tables in a table group to decide the stage usage for
		one table group.
		Input: table group list (type=List)
		Output: stage_num (type=Int)
		"""
		global TCAM_BLOCK_PER_STAGE, SRAM_BLOCK_PER_STAGE 
		stage_num = 0
		for table_group in table_groups:
			# new table group must at least take one stage
			tcam_usage = 0.000
			sram_usage = 0.000
			for table_name in table_group:
				if table_name in tcam_usage_dict:
					tcam_usage += tcam_usage_dict[table_name]
				elif table_name in sram_usage_dict:
					sram_usage += sram_usage_dict[table_name]
			if tcam_usage==0 and sram_usage==0:
				stage_num += 1
			else:
				stage_num += max(int(math.ceil( float(tcam_usage)/TCAM_BLOCK_PER_STAGE )), \
					int(math.ceil( float(sram_usage)/SRAM_BLOCK_PER_STAGE )))
		return stage_num


def test_profile_p4(test_id=0):
	os.chdir('../')
	# test case 0: give p4 file
	checker = p4_usage_checker('nf.p4', [], 12)
	print(checker.NFCP_check_p4_stage_usage(), checker.stage_usage)

	return
	# test case 1: default log file (None p4_list)
	checker = p4_usage_checker(None, [], 12)
	print(checker.NFCP_check_p4_stage_usage(), checker.stage_usage)
	
	# test case 2: really large table usage
	checker = p4_usage_checker('./core/sh_wo.p4', [], 12)
	print(checker.NFCP_check_p4_stage_usage(), checker.stage_usage)

	# test case 3: really large table usage
	#checker = p4_usage_checker('../nf.p4', [], 12)
	#print(checker.NFCP_check_p4_stage_usage(), checker.stage_usage)
	return

if __name__ == '__main__':
	test_profile_p4()
