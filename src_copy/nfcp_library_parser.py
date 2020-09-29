
"""
* NFCP_LIBRARY_PARSER.PY
* This script is used to parse a single P4 library.
* Several things to process: headers, parser, deparser, ingress/egress code
*
* Author: Jianfeng Wang
* Time: 02-26-2018
* Email: jianfenw@usc.edu
*
"""

from __future__ import print_function
import os
import subprocess
import collections
import copy
import p4_lib_parser.header as header
import p4_lib_parser.my_parser as MyParser
import p4_lib_parser.ingress_match_action as MyIngress
import p4_lib_parser.egress_match_action as MyEgress
import p4_lib_parser.my_deparser as MyDeparser
import util.lang_parser_helper as lang_helper
from util.nfcp_nf_node import *


'''
<NFCP Lib language>
- Provide a list like database for each P4 code
- P4 Code -> P4 Lib -> P4 NF Node -> P4 Code
- NFCP P4 Code Generator can generate P4 code based on the modified P4 nf_node.
'''

class nfcp_lib_parser(object):
	def __init__(self, lib_filename, nf_node):
		self.lib_filename = None
		self.nf_node = nf_node
		if lib_filename != None:
			self.lib_parser_process(lib_filename)
		return

	def lib_parser_process(self, lib_filename):
		if lib_filename != None:
			self.lib_filename = copy.deepcopy(lib_filename)
			self.lib_parser_main()
		return

	def lib_parser_main(self):
		self.lib_parser_handle_const_var()
		self.lib_parser_handle_header()
		self.lib_parser_handle_metadata()
		self.lib_parser_handle_parser_state()
		self.lib_parser_handle_ingress()
		self.lib_parser_handle_deparser_state()
		return

	def lib_parser_handle_const_var(self):
		cp = header.const_var_parser()
		cp.read_macros( self.lib_filename )
		self.nf_node.nf_node_store_macro( cp.macro_list )
		
		cp.read_const_variables( self.lib_filename )
		self.nf_node.nf_node_store_const( cp.const_list )
		return

	def lib_parser_handle_header(self):
		hp = header.header_parser([], collections.OrderedDict())
		hp.read_headers(self.lib_filename)
		self.nf_node.nf_node_store_header(hp.headers)
		return

	def lib_parser_handle_metadata(self):
		hp = header.header_parser([], collections.OrderedDict())
		hp.read_metadata(self.lib_filename)
		self.nf_node.nf_node_store_metadata(hp.metadata)
		return

	def lib_parser_handle_parser_state(self):
		mpp = MyParser.myparser()
		mpp.read_transition_rules(self.lib_filename)
		for state in mpp.state_list:
			if state.branch_num != len(state.transition_info):
				print("Error:", state.name, state.branch_num, state.transition_info)
		self.nf_node.nf_node_store_parser_state(mpp.state_list)
		return

	def lib_parser_handle_ingress(self):
		ingress = MyIngress.ingress_match_action()
		ingress.read_default_prefix(self.lib_filename)
		ingress.read_field_operations(self.lib_filename)
		ingress.read_ingress(self.lib_filename)
		#print(ingress.field_list_set, ingress.field_list_calc_set)
		'''
		# Merge three functions into one 'read_ingress'
		ingress.read_actions( self.lib_filename )
		ingress.read_tables( self.lib_filename )
		ingress.read_apply_rule( self.lib_filename )
		'''
		self.nf_node.nf_node_store_ingress_code( ingress.output_prefix, \
			ingress.field_list_set, ingress.field_list_calc_set, \
			ingress.action_set, ingress.table_set, ingress.apply_rule )
		return
		
	def lib_parser_handle_deparser_state(self):
		mdp = MyDeparser.mydeparser()
		mdp.read_deparser_rules( self.lib_filename )
		self.nf_node.nf_node_store_deparser(mdp.deparser_seq)
		return

def nfcp_library_parser_handle_const_var(library_filename, nf_node):
	cp = header.const_var_parser()
	cp.read_macros( library_filename )
	nf_node.nf_node_store_macro( cp.macro_list )
	cp.read_const_variables( library_filename )
	nf_node.nf_node_store_const( cp.const_list )
	return

def nfcp_library_parser_handle_header(library_filename, nf_node):
	hp = header.header_parser([], collections.OrderedDict())
	"""
	print hp.headers, hp.metadata
	if library_filename == './p4_lib/silkroad.lib':
		hp.metadata['a'] = 1
	"""
	hp.read_headers( library_filename )
	#print "Library Headers:", hp.headers
	nf_node.nf_node_store_header(hp.headers)
	return

def nfcp_library_parser_handle_metadata(library_filename, nf_node):
	hp = header.header_parser([], collections.OrderedDict())
	hp.read_metadata( library_filename )
	#print "nfcp single library parser: metadata -", hp.metadata
	nf_node.nf_node_store_metadata(hp.metadata)
	return

def nfcp_library_parser_handle_parser_state(library_filename, nf_node):
	mpp = MyParser.myparser()
	#print "enter parser state:", len(mpp.state_list)
	mpp.read_transition_rules( library_filename )
	for state in mpp.state_list:
		if state.branch_num != len(state.transition_info):
			error_msg = "Error: %s has a wrong branch num %d" %(state.name, state.branch_num)
			raise Exception(error_msg)
	nf_node.nf_node_store_parser_state(mpp.state_list)
	return

def nfcp_library_parser_handle_deparser_state(library_filename, nf_node):
	mdp = MyDeparser.mydeparser()
	mdp.read_deparser_rules( library_filename )
	#print "nfcp single library parser: deparser header list -", mdp.deparser_seq
	nf_node.nf_node_store_deparser(mdp.deparser_seq)
	return

def nfcp_library_parser_handle_ingress(library_filename, nf_node):
	ingress = MyIngress.ingress_match_action()
	ingress.read_default_prefix( library_filename )
	ingress.read_actions( library_filename )
	ingress.read_tables( library_filename )
	ingress.read_apply_rule( library_filename )
	nf_node.nf_node_store_ingress_code( \
		ingress.output_prefix, ingress.action_set, \
		ingress.table_set, ingress.apply_rule )
	return

def nfcp_library_parser_tester():
	print("NFCP Library Parser begins:")

	# Test nf_node data structure
	exam_node_1 = nf_node()
	exam_node_1.setup_node_from_argument(None, "SilkRoad", 1, 1)
	print('name:%s class:%s spi:%d si:%d' %(exam_node_1.name, exam_node_1.nf_class, exam_node_1.service_path_id, exam_node_1.service_id))
	
	examp_p4_lib_1 = "./p4_lib/silkroad.lib"
	nfcp_library_parser_handle_header(examp_p4_lib_1, exam_node_1)
	print(exam_node_1.header_list)

	exam_p4_lib_2 = "./p4_lib/acl.lib"
	exam_node_2 = nf_node()
	exam_node_2.setup_node_from_argument(None, "ACL", 1, 2)
	print('name:%s class:%s spi:%d si:%d' %(exam_node_2.name, exam_node_2.nf_class, exam_node_2.service_path_id, exam_node_2.service_id))
	nfcp_library_parser_handle_header(exam_p4_lib_2, exam_node_2)
	print("Headers -", exam_node_2.header_list)

	exam_node_2 = nf_node()
	exam_node_2.setup_node_from_argument(None, "ACL", 1, 3)
	lib_parser = nfcp_lib_parser(exam_p4_lib_2, exam_node_2)
	print("Headers -", exam_node_2.header_list)

	print("NFCP Single Library Parser ends")
	return


if __name__ == "__main__":
	nfcp_library_parser_tester()

