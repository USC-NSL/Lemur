"""
* 
* Title: nfcp_chain_parser.py 
* Description:
* This script is used to parse the NFCP user-level configuration file.
* 
* The user-level configuration file looks like the following - 
* L2 -> L3 -> ACL
* (The NF chain contains 3 network functions, i.e. L2, L3, and ACL)
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
* Time: 01/19/2017
* Email: jianfenw@usc.edu
*
* Author: Jane Yen
* Time: 03/12/2018
* Email: yeny@usc.edu
*
"""

import os
import subprocess
import collections
import util.lang_parser_helper as lang_helper
from util.lemur_nf_node import *

'''
<NFCP script language>
- Provide a Click-like module connection semantics
- All syntactic sugars must be able to co-exist with original Python syntax.
--------------------------------------------------------------------------------
No.		Syntax 						Semantics 				
--------------------------------------------------------------------------------
1		a -> b 						Connect module a and b
2		{'TCP', 'dport', '1000'}	Define a traffic type
3		{} : a -> b -> c 			Assign a traffic type to a network function chain
4		traff_a::{}					Assign a nickname to a traffic type
5		traff_a : a -> b -> c 		Assign a traffic name to a network function chain
6 		nick_name::standard_name 	Assign a nickname to a standard name
7 		a -> nick_name -> b 		Use a nickname to represent a standard module
'''

def trim_nickname_arg(input_str):
	"""
	This function is used to parse the nickname for a module
	e.g. fw::Firewall (fw is the nick name)
	"""
	cut = 0
	for cut in range(len(input_str)):
		if (cut+2) < len(input_str):
			if (input_str[cut] == ':') and (input_str[cut+1] == ':'):
				module_str = input_str[cut+2:].strip()
	return module_str

def trim_name_arg(input_str):
	module_name = None
	module_arg = None
	number = 0
	number2 = len(input_str)-1
	s_index = 0
	e_index = len(input_str)-1
	if (input_str.count('(')>0):
		for number in range(len(input_str)-1):
			if (input_str[number] == '('):
				s_index = number
				break
		while number2 >= 0:
			if(input_str[number2] == ')'):
				e_index = number2
				break
			else:
				number2 -= 1
		module_name = input_str[:s_index].strip()
		module_arg = input_str[s_index+1:e_index].strip()
	else:
		module_name = input_str
	return module_name, module_arg
			
"""
	nf_chain_parse_line:
	This function gets called when a line contains one or more '->'.
	It is used to parse the line and help generate the P4 list and the BESS list.
	Note: a valid line contains at least one '->' 
	(to connect the Source() module and the Sink() module, i.e. input and output ports)
"""
def nf_chain_parse_line(input_str, service_path_id, arg_list):
	#print "Arg list:", arg_list
	res_p4_list = []
	res_bess_list = []
	curr_service_path = service_path_id
	curr_nf_index = 1

	nsh_encap_flag = True
	s_index = 0
	e_index = 0
	for e_index in range(len(input_str)):
		if e_index+1 < len(input_str):
			if input_str[e_index] == '-' and input_str[e_index+1] == '>':
				curr_nf_str = input_str[s_index:e_index].strip()
				curr_nf_name, arg_str = trim_name_arg(curr_nf_str)
				e_index += 2
				s_index = e_index
				if curr_nf_name in arg_list:
					#print "find "+ curr_nf_name + " in arg_list"
					nickname_str = arg_list[curr_nf_name]
					module_def = trim_nickname_arg(nickname_str)
					module_name, module_arg = trim_name_arg(module_def)
					new_nf_node = nf_node(module_name.strip(), curr_service_path, curr_nf_index)
					new_nf_node.nf_node_store_arg(module_arg.strip())
					new_nf_node.nf_node_store_nickname(curr_nf_name.strip())
					"""
					print "///node checking///"
					print new_nf_node.name
					print new_nf_node.arg
					print new_nf_node.nickname
					print "///end checking///"
					"""
				else:
					new_nf_node = nf_node( curr_nf_name, curr_service_path, curr_nf_index )
					if arg_str != None:
						new_nf_node.nf_node_store_arg(arg_str.strip())
				#print "node: "+ str(new_nf_node.name) +" , node_type: "+ str(new_nf_node.nf_type)+ ", spi= "+ str(new_nf_node.service_path_id)+ ", si= "+ str(new_nf_node.service_id) + "\n"
				if new_nf_node.is_p4():
					res_p4_list.append(new_nf_node)
					nsh_encap_flag = True
				elif new_nf_node.is_bess():
					res_bess_list.append(new_nf_node)
					if nsh_encap_flag:
						nsh_encap_node = nf_node('NSHEncap', curr_service_path, curr_nf_index)
						res_p4_list.append(nsh_encap_node)
						nsh_encap_flag = False
				curr_nf_index += 1

	curr_nf_name = input_str[s_index:].strip()
	new_nf_node = nf_node( curr_nf_name, curr_service_path, curr_nf_index )
	if new_nf_node.is_p4():
		res_p4_list.append(new_nf_node)
	elif new_nf_node.is_bess():
		res_bess_list.append(new_nf_node)
		if nsh_encap_flag:
			nsh_encap_node = nf_node('NSHEncap', curr_service_path, curr_nf_index)
			res_p4_list.append(nsh_encap_node)
			nsh_encap_flag = False

	return res_p4_list, res_bess_list

def nf_fn_parse_line(arg_str):
	"""
	This function is used to parse 'Nickname::Standard_name'
	"""
	cut = 0
	len_n = len(arg_str)
	for cut in range(len_n-2):
		if arg_str[cut] == ':' and arg_str[cut+1] == ':' :
			key = arg_str[:cut].strip()
	return key

def nf_arg_parse_line(arg_str):
	"""
	Separate key and value for argument parsing
	equal_mark_pos = arg_str.index('=')
	key = arg_str[:equal_mark_pos].strip()
	return key
	"""
	token = 0
	for token in range(len(arg_str)):
		if (token+1) < len(arg_str):
			if arg_str[token] == '=':
				key = arg_str[:token].strip()
#                value = arg_str[token+1:].strip()
#            else:
#                print 'no/invalud value set for key'
	return key

def nf_chain_parser_main(config_filename):
	"""
	This function is used to parse the 'config_filename' to generate the two NF lists
	Note: one list is for BESS nodes, the other one is for P4 nodes
	"""
	nf_chain_seq = []
	nf_chain_dict = {}
	res_nf_chain_info = [nf_chain_seq, nf_chain_dict]
	res_p4_list = []
	res_bess_list = []
	arg_list = {}

	# service_path_id starts from 1. service_id starts from 1
	cmt_flag = False
	service_path_id = 0
	with open(config_filename, 'r') as fp:
		line_count = 0
		for line in fp:
			line_count += 1
			if lang_helper.is_empty_line(line):
				continue
			if "/*" in line:
				cmt_flag = True
			if "*/" in line:
				cmt_flag = False
				continue
			if cmt_flag:
				continue

			# Parse arguments
			if line.count('=') == 1:
				arg_key, arg_value = lang_helper.user_parser_nickname(line)
				nf_chain_def = lang_helper.user_parser_traffic_type(arg_value)
				if nf_chain_def: # this is a nf_chain definition
					print 'nf_chain_def: %s' %(nf_chain_def)
					nf_chain_dict[arg_key] = nf_chain_def
				else: # this is an argument definition (nf_chain_def == None)
					arg_list[arg_key] = line
					#print "get a key: %s, the value: %s" %(arg_key, arg_list[arg_key])
			# Parse NF service path definition
			else:
				service_path_id += 1
				curr_traffic, curr_nf_chain = lang_helper.user_parser_nf_chain(line)
				t_p4_list, t_bess_list = nf_chain_parse_line(curr_nf_chain, service_path_id, arg_list)
				#print t_p4_list
				res_p4_list += t_p4_list
				res_bess_list += t_bess_list
				nf_chain_seq.append(curr_traffic)
	return ( res_nf_chain_info, res_p4_list, res_bess_list, arg_list )


def nf_chain_parser_tester():
	print "NF Chain Parser begins:"
	
	print "List all user-level configuration scripts:"
	subprocess.call(['ls', './user_level_examples'])
	# return # for test subprocess

	config_filename = raw_input("Please input the NF chain configuration filename:\n")
	final_p4_name = config_filename[:config_filename.index(".")]
	final_p4_filename = final_p4_name.strip() + ".p4"
	
	nf_chain_info, p4_list, bess_list, argument_list = nf_chain_parser_main('./user_level_examples/'+config_filename)
	print "# of P4 modules:", len(p4_list), "# of BESS modules:", len(bess_list)
	
	# Test whether the service_path_id and service_id are correctly set up.
	print "All P4 modules:" 
	for node in p4_list:
		print node
	
	return # to test parsing of P4 modules

	print "All BESS modules:"
	for node in bess_list:
		print node

	print "NF Chain Parser Tester ends!"
	return # to test parsing of BESS modules



if __name__ == "__main__":
	nf_chain_parser_tester()



