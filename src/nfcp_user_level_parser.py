
"""
* 
* Title: nfcp_user_level_parser.py
* Description:
* This script is used to parse the NFCP user-level configuration file.
* In fact, the parser is a class that encapsulates the language lexer, parser, and
* other logic. Most of language-related functions are provided by the 'scanner'.
* Other member functions help the rest of our pipeline.
* 
* Author: Jianfeng Wang
* Time: 06/19/2018
* Email: jianfenw@usc.edu
*
"""

from __future__ import print_function
import sys
import os
import subprocess
import collections
import copy
from util.nfcp_nf_node import *
from util.lang_parser_helper import *
from antlr4 import *
from user_level_parser.NFCPUserLexer import NFCPUserLexer
from user_level_parser.NFCPUserParser import NFCPUserParser
from user_level_parser.NFCPUserListener import NFCPUserListener
from user_level_parser.UDNFCPUserListener import UDNFCPUserListener, linkedlist_node, convert_nf_graph, convert_global_nf_graph

'''
<NFCP script language>
- Provide a Click-like module connection semantics
- All syntactic sugars must be able to co-exist with original Python syntax.
--------------------------------------------------------------------------------
No.		Syntax 						Semantics 				
--------------------------------------------------------------------------------
1		{'dst_ip':'1.0.1.1'}		Define a flowspec
2		traffic : [{}, {}]			Define a flowspec instance
3 		instance_name = nf_module()	Define a NF instance
4		a -> b 						Connect module a with b
5 		a() -> instance -> b() 		Use a instance to represent a standard module
6		traff_a : a -> b -> c 		Assign a traffic name to a network function chain

* Please see NFCP language book to get more details. *
'''

class nfcp_config_parser(object):
	def __init__(self, conf_filename=None):
		self.conf_filename = None
		self.scanner = None
		self.total_chain_count = -1
		self.p4_list = None
		if conf_filename != None:
			self.conf_parser_process(conf_filename)
		return

	def conf_parser_process(self, conf_filename):
		if conf_filename != None:
			self.conf_filename = copy.deepcopy(conf_filename)
			self.conf_parser_main(self.conf_filename)
		return

	def conf_parser_main(self, conf_filename):
		"""
		This function is used to parse the NFCP user-level configuration script.
		Please refer to the NFCP user-level language book to see all details.
		Input: filename (type=str)
		Output: scanner (type=UDNFCPUserListener)
		"""
		conf_input = FileStream(conf_filename)
		lexer = NFCPUserLexer(conf_input)
		print("Lang Lexer: OK")
		
		stream = CommonTokenStream(lexer)
		print("Lang Stream: OK")
		
		parser = NFCPUserParser(stream)
		print("Lang Parser: OK")
		
		tree = parser.total()
		scanner = UDNFCPUserListener()
		walker = ParseTreeWalker()
		walker.walk(scanner, tree)
		print("Lang ParseTree Walker: OK") 
		self.scanner = scanner
		convert_global_nf_graph(self.scanner)
		return

	def conf_parser_get_all_nodes(self):
		"""
		Description: return all P4 and BESS nodes
		Input: None
		Output: a list of all nf_node
		"""

		res_node_list = []
		# nf_chains = [all chain's root ll_node's name]
		nf_chains = sorted(self.scanner.flowspec_nfchain_mapping.values())
		for chain_name in nf_chains:
			chain_ll_node = self.scanner.struct_nlinkedlist_dict[chain_name]
			chain_graph = convert_nf_graph(chain_ll_node)
			curr_chain_nodes = chain_graph.list_modules()
			res_node_list += curr_chain_nodes
		return res_node_list

	def conf_parser_get_p4_nodes(self, placement_decision):
		"""
		Description: return all necessary P4 nodes (including NSHEncap)
		Input: Placement decision
		Output: a list of P4 nf_node (type=list)
		"""
		res_p4_list = []
		nsh_encap_required = True

		all_graphs = self.conf_parser_get_all_graphs(placement_decision)
		for sp_name, sp_graph in all_graphs.items():
			'''
			if not sp_graph.check_shared_modules():
				continue
			'''
			# sp_graph.get_p4_nodes() gives the p4_list for the service path
			#print(len(sp_graph.get_p4_nodes()))
			res_p4_list.append(sp_graph.get_p4_nodes())
		return res_p4_list

	def conf_parser_get_global_p4_nodes(self, placement_decision):
		"""
		Description: return all necessary P4 nodes in global view
		:type placement_decision: List[nf_node]
		:rtype p4_node_lists: List[List[nf_node]]
		"""
		p4_node_lists = []
		global_graph = convert_global_nf_graph(self.scanner)
		global_graph_list = global_graph.list_modules()
		for idx in range(len(global_graph_list)):
			curr = global_graph_list[idx]
			comp_curr = placement_decision[placement_decision.index(curr)]
			curr.bind_node_nf_type(comp_curr.nf_type)

		p4_node_lists.append(global_graph.get_p4_nodes())
		return p4_node_lists

	def conf_parser_show_stats(self, logger):
		"""
		Description: call this function to show the statistics of the final data structs
		Input: logger (type(logger)==logging.Logger)
		Output: None
		"""
		logger.info("Conf Parser Stats:")
		all_graphs = self.conf_parser_get_all_graphs()
		logger.info(" - NF Chain: %d effective chains" %(len(all_graphs)))
		for sp_name, sp_graph in all_graphs.items():
			logger.info("\tchain[%s]: total %d nodes, %d P4 nodes" %(sp_name, len(sp_graph.list_modules()), len(sp_graph.get_p4_nodes())))
		return

	def conf_parser_get_bess_nodes(self):
		pass

	def conf_parser_get_all_graphs(self, placement_decision=None):
		"""
		Description: return all effective NF graphs
		Input: None
		Output: a list of nfchain_graph (type=list)
		"""
		res_graphs = {}
		for flowspec, nfchain in self.scanner.flowspec_nfchain_mapping.items():
			nfchain_ll_node = self.scanner.struct_nlinkedlist_dict[nfchain]
			res_graphs[nfchain] = convert_nf_graph(nfchain_ll_node)
			if placement_decision:
				for nf_node in res_graphs[nfchain].list_modules():
					op_nf_node = placement_decision[placement_decision.index(nf_node)]
					nf_node.bind_node_nf_type(op_nf_node.nf_type)
					#print(op_nf_node, nf_node.name, nf_node in placement_decision)
		return res_graphs


def nf_chain_parser_example_tester(input_parser, argv=None):
	"""
	nf_chain_parser_tester:
	This tester is aimed to test the user-level language parser.
	(1) basic data types
	(2) structed data types
	(3) define network functions
	(4) define flow spec
	(5) define network function service chain
	(5) configure NF chain with flowspec

	Input: None
	Output: None
	"""
	scanner = input_parser.scanner
	print("Tests for basic data types")
	print("# 1 Lookup Table for INT variables:", scanner.var_int_dict)
	print("# 2 Lookup Table for FLOAT variables:", scanner.var_float_dict)
	print("# 3 Lookup Table for STRING variables:", scanner.var_string_dict)
	print("# 4 Lookup Table for BOOL variables:", scanner.var_bool_dict)

	print("Tests for NetFunctions")
	print("# 5 Lookup Table for NetFunc instances:", scanner.func_dict)

	print("Tests for structured data types - ntuple, nlist, nlinkedlist")
	print("# 6 Lookup Table for ntuple instances:", scanner.struct_ntuple_dict)
	print("# 7 Lookup Table for nlist instances:", scanner.struct_nlist_dict)
	print("# 8 Lookup Table for nlinkedlist instances:", scanner.struct_nlinkedlist_dict)
	for name, ll_node in scanner.struct_nlinkedlist_dict.items():
		print('-', name, '-length', len(ll_node))

	print("# 9 Print a nlinkedlist:")
	print("  - sp_1:", scanner.struct_nlinkedlist_dict['sp_1'])
	print("print all nodes in netchain sp_1")
	service_path_1 = scanner.struct_nlinkedlist_dict['sp_1'].get_all_nodes()
	for node in service_path_1:
		print(node.instance, node.spi, node.si)

	print("  - sp_2:", scanner.struct_nlinkedlist_dict['sp_2'])
	print("print all nodes in netchain sp_2")
	service_path_2 = scanner.struct_nlinkedlist_dict['sp_2'].get_all_nodes()
	for node in service_path_2:
		print(node.instance, node.spi, node.si)

	print("# 10 Print a formatted Network Function Chain:")
	print('  - sp_1:\n', scanner.struct_nlinkedlist_dict['sp_1']._draw_pipeline())
	print('  - sp_2:\n', scanner.struct_nlinkedlist_dict['sp_2']._draw_pipeline())
	print('  - sp_3:\n', scanner.struct_nlinkedlist_dict['sp_3']._draw_pipeline())
	print('  - sp_4:\n', scanner.struct_nlinkedlist_dict['sp_4']._draw_pipeline())

	print("# 11 Statistics:")
	print('Total # of service paths:', scanner.service_path_count)
	#print scanner.overall_nf_chain_list
	print("NFCP User-Level Parser Finished!")

	#p4_list, bess_list = nf_chain_get_nf_node_list(scanner)
	return


def nf_chain_parser_tester(argv):
	print("NF Chain Parser begins:")
	print("List all user-level configuration scripts:")
	subprocess.call(['ls', './user_level_examples'])
	#config_filename = raw_input("Please input the NF chain configuration filename:\n")
	#p4_list, bess_list = nf_chain_parser_main('./user_level_examples/'+config_filename)
	config_filename = 'example.conf'
	test_parser = nfcp_config_parser(config_filename)
	nf_chain_parser_example_tester(test_parser)
	# Test whether the service_path_id and service_id are correctly set up
	#print("# of P4 modules: %d, # of BESS modules: %d" %( len(p4_list), len(bess_list) ))
	#for p4_node in p4_list:
	#	print "%s: sp=%d, sidx=%d" %(p4_node.name, p4_node.service_path_id, p4_node.service_id)
	return


if __name__ == '__main__':
	nf_chain_parser_tester(sys.argv)

