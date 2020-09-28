"""
* 
* NFCP_USER_LEVEL_PARSER.PY - 
* This script is used to parse the NFCP user-level configuration file.
* 
* The script will parse network functions in the NF chain.
* These NFs will be stored in two lists, one for P4 libraries and the other one for 
* BESS modules. 
* There are two modules that process the two sets seperately. For P4 libraries, the 
* P4 parser module will combine all P4 libraries together and output the final P4 code. 
* For BESS modules, the BESS parser module will generate a correct BESS configuration 
* file, which can be directly run in the BESS system (bessctl).
* 
* Author: Jianfeng Wang
* Time: 06-19-2018
* Email: jianfenw@usc.edu
*
"""
import sys
import os
import subprocess
import collections
import copy
from util.nfcp_nf_node import *
from util.lang_parser_helper import *
from antlr4 import *
from NFCPUserLexer import NFCPUserLexer
from NFCPUserParser import NFCPUserParser
from NFCPUserListener import NFCPUserListener
from UDNFCPUserListener import UDNFCPUserListener, linkedlist_node, convert_nf_graph


'''
<NFCP script language>
- Provide a Click-like module connection semantics
- All syntactic sugars must be able to co-exist with original Python syntax.
--------------------------------------------------------------------------------
No.		Syntax 						Semantics 				
--------------------------------------------------------------------------------
1		{'dst_ip':'1.0.1.1'}		Define a flowspec
2		traff_a : [{}, {}]			Define a flowspec instance
3 		instance_name = nf_module()	Define a NF instance
4		a -> b 						Connect module a with b
5 		a() -> instance -> b() 		Use a instance to represent a standard module
6		traff_a : a -> b -> c 		Assign a traffic name to a network function chain

'''





def nf_chain_get_all_nodes(scanner):
	res_p4_list = []
	nsh_encap_required = True
	
	# nf_chains = [all chain's root ll_node]
	nf_chains = scanner.flowspec_nfchain_mapping.values()
	nf_chain_graphs = []
	for curr_chain_name in nf_chains:
		curr_chain = scanner.struct_nlinkedlist_dict[curr_chain_name]
		curr_chain_graph = convert_nf_graph(curr_chain)
		curr_nodes = curr_chain_graph.list_modules()
		res_p4_list += curr_nodes
		print ' - %s modules in chain "%s"' %(len(curr_nodes), curr_chain_name)

	print "# of nodes:", len(res_p4_list)
	return
	#return res_p4_list


def nf_chain_get_p4_nodes(scanner):
	res_p4_list = []
	nsh_encap_required = True
	
	# nf_chains = [all chain's root ll_node]
	nf_chains = scanner.flowspec_nfchain_mapping.values()
	nf_chain_graphs = []
	for curr_chain in nf_chains:
		curr_chain_graph = convert_nf_graph(curr_chain)
		curr_nodes = curr_chain_graph.list_modules()
		res_p4_list += curr_nodes

	print "# of nodes:", len(res_p4_list)
	return res_p4_list


def nf_chain_get_bess_nodes(scanner):
	return None


def nf_chain_get_nf_node_graph(scanner):
	return


def nf_chain_parser_main(config_filename):
	"""
	This function is used to parse the NFCP user-level configuration script.
	Please refer to the NFCP user-level language book to see all details.
	Input: filename(type=str)
	Output: scanner (UDNFCPUserListener)
	"""

	conf_input = FileStream(config_filename)
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
	print("ParseTree Walker: OK")
	
	return scanner


def nf_chain_parser_example_tester(input_scanner, argv=None):
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
	scanner = input_scanner

	print "Tests for basic data types"
	print "# 1 Lookup Table for INT variables:", scanner.var_int_dict
	print "# 2 Lookup Table for FLOAT variables:", scanner.var_float_dict
	print "# 3 Lookup Table for STRING variables:", scanner.var_string_dict
	print "# 4 Lookup Table for BOOL variables:", scanner.var_bool_dict

	print "Tests for NetFunctions"
	print "# 5 Lookup Table for NetFunc instances:", scanner.func_dict

	print "Tests for structured data types - ntuple, nlist, nlinkedlist"
	print "# 6 Lookup Table for ntuple instances:", scanner.struct_ntuple_dict
	print "# 7 Lookup Table for nlist instances:", scanner.struct_nlist_dict
	print "# 8 Lookup Table for nlinkedlist instances:", scanner.struct_nlinkedlist_dict
	for key, val in scanner.struct_nlinkedlist_dict.items():
		print '-', key, '-length', val.get_length()

	#print "# 9 Print a nlinkedlist w/o branches:"
	#print "- linkedlist_a:", scanner.struct_nlinkedlist_dict['linkedlist_a']
	#print "- linkedlist_b:", scanner.struct_nlinkedlist_dict['linkedlist_b']
	print "# 10 Print a nlinkedlist:"
	print "  - sp_1:", scanner.struct_nlinkedlist_dict['sp_1']
	print "print all nodes in netchain sp_1"
	service_path_1 = scanner.struct_nlinkedlist_dict['sp_1'].get_all_nodes()
	for node in service_path_1:
		print node.instance, node.spi, node.si

	print "  - sp_2:", scanner.struct_nlinkedlist_dict['sp_2']
	print "print all nodes in netchain sp_2"
	service_path_2 = scanner.struct_nlinkedlist_dict['sp_2'].get_all_nodes()
	for node in service_path_2:
		print node.instance, node.spi, node.si

	print "# 11 Print a formatted Network Function Chain:"
	print '  - sp_1:\n', scanner.struct_nlinkedlist_dict['sp_1']._draw_pipeline()
	print '  - sp_2:\n', scanner.struct_nlinkedlist_dict['sp_2']._draw_pipeline()
	print '  - sp_3:\n', scanner.struct_nlinkedlist_dict['sp_3']._draw_pipeline()
	print '  - sp_4:\n', scanner.struct_nlinkedlist_dict['sp_4']._draw_pipeline()

	print "# 12 Statistics:"
	print 'Total # of service paths:', scanner.service_path_count
	print 'Total # of NF moduels', nf_chain_get_all_nodes(scanner)
	#print scanner.overall_nf_chain_list
	print("NFCP User-Level Parser Finished!")

	#p4_list, bess_list = nf_chain_get_nf_node_list(scanner)
	return


def nf_chain_parser_tester(argv):
	print "NF Chain Parser begins:"
	print "List all user-level configuration scripts:"
	subprocess.call(['ls', './user_level_examples'])

	#config_filename = raw_input("Please input the NF chain configuration filename:\n")
	#p4_list, bess_list = nf_chain_parser_main('./user_level_examples/'+config_filename)
	config_filename = 'example.conf'
	example_scanner = nf_chain_parser_main(config_filename)
	nf_chain_parser_example_tester(example_scanner)
	# Test whether the service_path_id and service_id are correctly set up
	#print("# of P4 modules: %d, # of BESS modules: %d" %( len(p4_list), len(bess_list) ))
	#for p4_node in p4_list:
	#	print "%s: sp=%d, sidx=%d" %(p4_node.name, p4_node.service_path_id, p4_node.service_id)
	return


if __name__ == '__main__':
	nf_chain_parser_tester(sys.argv)





