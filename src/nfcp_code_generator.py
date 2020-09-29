
"""
* NFCP_CODE_GENERATOR.PY
* The script can receive the combined lists/dicts of information from the NFCP combiner.
* It will generate the corresponding P4 code.
* (1) use header.py to generate header code
* (2) use my_parser.py to generate parser code
* (3) use ingress_match_action.py to generate ingress code
* (4) (the same for egress)
* (5) use my_deparser.py to generate deparser code
* (6) other pieces of code
*
* Author: Jianfeng Wang
* Time: 02-27-2018
* Email: jianfenw@usc.edu
*
"""

from __future__ import print_function
import os
import subprocess
import collections
import logging
import p4_lib_parser.header as header
import p4_lib_parser.my_parser as MyParser
import p4_lib_parser.ingress_match_action as MyIngress
import p4_lib_parser.egress_match_action as MyEgress
import p4_lib_parser.my_deparser as MyDeparser
import p4_lib_parser.my_verifychecksum as MyVerifyChecksum
import p4_lib_parser.my_computechecksum as MyComCheckSum
import p4_lib_parser.v1_switch_main as MySwitchMain
from user_level_parser.UDLemurUserListener \
    import convert_nf_graph, convert_global_nf_graph
from util.lang_parser_helper import *
from util.lemur_nf_node import *
from util.lemur_codegen_helper import *

# P4 constant string literals
p414_egress_start = '\n/************************  E G R E S S  **********************************/\n'
p414_ingress_start = '\n/************************  I N G R E S S  **********************************/\n'
p414_preprocess_nsh = "\tif (valid(nsh)) {\n\
\t\tapply(sys_remove_nsh_header_apply);\n\
\t}\n"

p414_packet_destine = "\tif ( (meta.controller_flag == 1) or (meta.nsh_flag == 1) ) {\n\
\t\tapply(sys_valid_nsh_header_apply);\n\
\t\tif(valid(vlan)) {\n\
\t\t\tapply(sys_handle_next_proto_vlan_apply);\n\
\t\t}\n\
\t\telse {\n\
\t\t\tapply(sys_handle_next_proto_ipv4_apply);\n\
\t\t}\n\
\t}\n\
\tif (meta.nsh_flag==1) {\n\
\t\tapply(sys_send_to_bess_apply);\n\
\t}\n\
\tif (meta.controller_flag==1) {\n\
\t\tapply(sys_send_to_controller_apply);\n\
\t}\n\
\tif (meta.drop_flag==1) {\n\
\t\tapply(sys_drop_apply);\n\
\t}\n"

p414_nf_update_si = "\tif( (meta.controller_flag == 1) or (meta.nsh_flag == 1) ) {\n\
\t}\n\
\telse {\n\
\t\tapply(_update_si_apply);\n\
\t}\n"

p414_nf_update_spi = "\tif( (meta.controller_flag == 1) or (meta.nsh_flag == 1) ) {\n\
\t}\n\
\telse {\n\
\t\tapply(_update_spi_apply);\n\
\t}\n"


class control_flow_graph(object):
	def __init__(self):
		self.root = control_flow_node((0,0))
		self.control_flow_count = 0
		self.cf_node_list = []
		return

	def get_root(self):
		return (self.root)

	def get_cf_node_list(self):
		""" Recursive-DFS traverse the control_flow_graph (tree). Generate a list that maintains the correct order of all control flow nodes.
		:rtype : List[control_flow_node] 
		"""
		self.get_cf_node_list_helper(self.root)
		return self.cf_node_list

	def get_cf_node_list_helper(self, curr_cf_node):
		""" The helper function (DFS traverser). For each depth in the control flow graph, it sorts the children nodes according to their control_flow_idx.
		(Note: merge/share nodes -> inf; individual nodes -> int (0, 1, 2, and so on ...))
		"""
		if curr_cf_node != self.root:
			self.cf_node_list.append(curr_cf_node)

		curr_cf_node.next.sort(key = lambda cf_node: cf_node.control_flow_idx)
		for node in curr_cf_node.next:
			self.get_cf_node_list_helper(node)
		return

	def add_cf_node(self, cf_node):
		"""
		Find the correct parent node for cf_node. Then, call self.add_cf_edge(src, dst) to link them together.
		:type cf_node: control_flow_node
		"""
		cf_node_parent = self.root
		if cf_node.entry_flag:
			cf_node_parent = self.root
		else:
			parent_list = []
			for routing_info in cf_node.ancestors:
				parent_node = self.locate_cf_node(routing_info)
				if parent_node:
					parent_list.append(parent_node)
			cf_node_parent = self.get_cf_node_parent(parent_list)
		self.add_cf_edge(cf_node_parent, cf_node)
		return

	def get_cf_node_parent(self, parent_node_list):
		""" This function 'BFS' traverses the graph to find the parent of all nodes in parent_node_list.
		It returns when reaching the first correct node. If no cf_node satisfies the requirement, then it returns None.
		"""
		res_node = None
		cf_node_queue = [self.root]
		tmp_queue = []
		while len(cf_node_queue)>0:
			for cf_node in cf_node_queue:
				if cf_node.check_reachable_nodes(parent_node_list):
					res_node = cf_node
				tmp_queue += cf_node.next
			cf_node_queue = tmp_queue
			tmp_queue = []
		return res_node

	def locate_cf_node(self, routing_info):
		"""
		Find (BFS) the parent node for an inserted cf_node based on its routing info
		:type routing_info: List[(spi, si)]
		:rtype rnode: control_flow_node
		"""
		res_node = None
		'''
		for node in self.root.next:
			res_node = self.locate_cf_node_helper(node, routing_info)
			if res_node:
				return res_node
		'''
		res_node = self.locate_cf_node_helper(self.root, routing_info)
		return res_node

	def locate_cf_node_helper(self, curr_cf_node, routing_info):
		if curr_cf_node.find(routing_info):
			return curr_cf_node
		else:
			for cf_node in curr_cf_node.next:
				res_node = self.locate_cf_node_helper(cf_node, routing_info)
				if res_node:
					return res_node
			return None

	def add_cf_edge(self, src, dst):
		"""
		:type src: control_flow_node 
		:type dst: control_flow_node
		:rtype: None
		"""
		src.next.append(dst)
		dst.prev = src
		dst.control_flow_layer = src.control_flow_layer+1
		dst.reachable_nodes.append(dst)

		if dst.is_merge_node:
			dst.control_flow_idx = float('inf')
		else:
			dst.control_flow_idx = src.branch_count
			src.branch_count += 1

		ancestor_cf_node = src
		while ancestor_cf_node:
			ancestor_cf_node.reachable_nodes.append(dst)
			ancestor_cf_node = ancestor_cf_node.prev
		return


class control_flow_node(object):
	def __init__(self, routing_info):
		self.routing_info = routing_info
		self.need_routing = True
		self.is_merge_node = False
		# if self.entry_flag==True, this control flow node MUST be attached to the root of control flow graph
		self.entry_flag = False
		# control_flow_layer: layer (depth) of the node in control flow graph
		# control_flow_idx: index (breadth) of the node as the children of another node
		self.control_flow_layer = 0
		self.control_flow_idx = 0
		self.branch_count = 0

		# nf_node_list: all NF nodes associated with the control flow node
		# shared_node_list: all shared NF nodes associated with the control flow node
		self.nf_node_list = []
		self.shared_node_list = []
		self.nf_node_count = 0
		self.shared_node_count = 0
		self.next = []
		self.prev = None
		self.ancestors = []
		# update all nodes that can reach the node
		self.reachable_nodes = []
		return

	def get_routing_info(self):
		spi, si = self.routing_info
		if (self.control_flow_idx==0) or (self.is_merge_node):
			res_node = '\t'*self.control_flow_layer+'if (meta.service_path_id==%d and meta.service_id==%d and meta.drop_flag==0 and meta.controller_flag==0) {\n' %(spi, si)
		else:
			res_node = '\t'*self.control_flow_layer+'else if (meta.service_path_id==%d and meta.service_id==%d and meta.drop_flag==0 and meta.controller_flag==0) {\n' %(spi, si)
		return res_node

	def __cmp__(self, other_node):
		if (self.routing_info[0] < other_node.routing_info[0]):
			return -1
		elif (self.routing_info[0] > other_node.routing_info[0]):
			return 1
		else:
			if (self.routing_info[1] < other_node.routing_info[1]):
				return -1
			elif (self.routing_info[1] > other_node.routing_info[1]):
				return 1
			else:
				return 0

	def __str__(self):
		return 'control_node[spi=%d,si=%d,enty=%d,ly=%d]' %(self.routing_info[0], self.routing_info[1], self.entry_flag, self.control_flow_layer)

	def find(self, target_routing_info):
		spi, si = target_routing_info[0], target_routing_info[1]
		for node in self.nf_node_list:
			if node.service_path_id==spi and node.service_id==si:
				return True
		return False

	def update_ancestors(self, nf_node):
		for parent_node in nf_node.prev_nodes:
			if (not self.entry_flag) and parent_node.is_bess():
				self.entry_flag = True
			self.ancestors.append((parent_node.service_path_id, parent_node.service_id))
		if len(self.ancestors) == 0:
			self.entry_flag = True
		if len(self.ancestors) > 1:
			self.is_merge_node = True
		return

	def check_reachable_nodes(self, parent_list):
		""" This function returns whether all nodes in parent_list can reach the current node or not.
		"""
		for node in parent_list:
			if node not in self.reachable_nodes:
				#print('Note: %s cannot reach %s in parent_list' %(self, node))
				return False
		return True

	def add_nf_node(self, nf_node):
		""" Associate a nf_node with the current control flow node.
		First, update self.nf_node_list. Second, update self.shared_node_list if it is a shared NF.
		"""
		if len(self.nf_node_list)==0:
			self.update_ancestors(nf_node)
		self.nf_node_list.append(nf_node)
		self.nf_node_count += 1
		if nf_node.is_shared_module():
			self.shared_node_list.append(nf_node)
			self.shared_node_count += 1
		return
	
	"""
	def add_nf_node_list(self, nf_node_list):
		for nf_node in nf_node_list:
			self.add_nf_node(nf_node)
		return
	"""

class nfcp_code_generator(object):
	def __init__(self, scanner, p4_list, p4_version):
		self.scanner = copy.deepcopy(scanner)
		self.p4_list = copy.deepcopy(p4_list)
		self.p4_version = copy.deepcopy(p4_version)

		self.nf_lookup_table = None
		self.macro_list = None
		self.const_list = None
		self.header_list = None
		self.metadata_dict = None
		self.parser_state_list = None
		self.action_prefix_set = None
		self.table_prefix_set = None
		self.field_list_set = None
		self.field_list_calc_set = None
		self.ingress_action_set = None
		self.ingress_table_set = None
		self.ingress_apply_rule = None
		self.deparser_header_list = None
		return

	def lib_parsre_main(self):
		"""
		TO DO: merge lib_parser to the nfcp_code_generator
		"""
		return

	def lib_combine_main(self):
		"""
		Description: use 'nfcp_p4_library_combiner' to merge all P4 libraries
		Input: None
		Output: None (p4_nodes in self.p4_list are modified)
		"""
		self.lib_combine_init()

		all_deparser_list = []
		for p4_node in self.p4_list:
			# Merge macro definition
			for macro_key, macro_val in p4_node.macro_list.items():
				if macro_key not in self.macro_list:
					self.macro_list[macro_key] = macro_val

			# Merge const variables definition
			for const_name, const_def in (p4_node.const_list).items():
				if const_name not in self.const_list.keys():
					self.const_list[const_name] = const_def

			# Merge header and metadata definition
			for header in p4_node.header_list:
				if header not in self.header_list:
					self.header_list.append(header)
			for meta in p4_node.metadata_dict:
				if meta not in self.metadata_dict:
					self.metadata_dict[meta] = p4_node.metadata_dict[meta]
			
			for field_list in p4_node.field_lists:
				if field_list not in self.field_list_set:
					self.field_list_set[field_list] = p4_node.field_lists[field_list]

			for field_list_calc in p4_node.field_list_calcs:
				if field_list_calc not in self.field_list_calc_set:
					self.field_list_calc_set[field_list_calc] = p4_node.field_list_calcs[field_list_calc]

			for state in p4_node.parser_state_list:
				if state in self.parser_state_list: # if state exists, merge them
					self.state = self.parser_state_list[ self.parser_state_list.index(state) ]
					self.state.merge_state(state)
				else: # if state doesn't exist, add state to self.parser_state_list
					new_state = copy.deepcopy(state)
					self.parser_state_list.append(new_state)

			all_deparser_list.append(p4_node.deparser_header_list)

			# Update self.action_prefix_set, self.table_prefix_set
			self.action_prefix_set[p4_node.name] = p4_node.action_prefix
			if p4_node.service_path_id == 0:
				self.table_prefix_set[p4_node.name] = p4_node.action_prefix
			else:
				self.table_prefix_set[p4_node.name] = p4_node.action_prefix+"_%d_%d"%(p4_node.service_path_id, p4_node.service_id)
			
			# Merge actions, tables, and apply rules
			if (p4_node.name not in self.ingress_action_set):
				self.ingress_action_set[p4_node.name] = p4_node.ingress_actions
			if p4_node.name not in self.ingress_table_set:
				self.ingress_table_set[p4_node.name] = p4_node.ingress_tables
			if p4_node.name not in self.ingress_apply_rule:
				self.ingress_apply_rule[p4_node.name] = p4_node.ingress_apply_rule
			self.nf_lookup_table[p4_node.name] = p4_node.nf_class

		# Merge deparser lists
		self.deparser_list = lib_combiner_merge_list(all_deparser_list)
		return

	def lib_combine_init(self):
		"""
		Description: the function initializes the data structs to store headers,
		parser, actions, tables, apply rules, and deparser for the final P4 code.
		"""
		self.nf_lookup_table = {}
		self.macro_list = collections.OrderedDict()
		self.const_list = collections.OrderedDict()
		self.header_list = []
		self.metadata_dict = collections.OrderedDict()
		self.parser_state_list = []
		self.action_prefix_set = collections.OrderedDict()
		self.table_prefix_set = collections.OrderedDict()
		self.field_list_set = collections.OrderedDict()
		self.field_list_calc_set = collections.OrderedDict()
		self.ingress_action_set = collections.OrderedDict()
		self.ingress_table_set = collections.OrderedDict()
		self.ingress_apply_rule = collections.OrderedDict()
		self.deparser_list = []
		self.metadata_dict['service_path_id'] = "24"
		self.metadata_dict['service_id'] = "8"
		self.metadata_dict['prev_spi'] = "8"
		self.metadata_dict['prev_si'] = "8"
		self.metadata_dict['forward_flag'] = "1"
		self.metadata_dict['controller_flag'] = "1"
		self.metadata_dict['nsh_flag'] = "1"
		self.metadata_dict['drop_flag'] = "1"
		return

	def lib_combine_show_stats(self, logger):
		"""
		Description: call this function to show the statistics of the final data structs
		Input: logger (type(logger)==logging.Logger)
		Output: None
		"""
		logger.info("Lib Combiner Stats:")
		logger.info(" - myMacro: %s macros, %d const" %(len(self.macro_list), len(self.const_list)))
		logger.info(" - myHeader: %s" %(str(self.header_list)))
		logger.info(" - myParser: %d" %(len(self.parser_state_list)))
		logger.info(" - myIngress: %d actions, %d tables, %d apply rules" %(len(self.ingress_action_set), len(self.ingress_table_set), len(self.ingress_apply_rule)))
		for _name, _prefix in self.action_prefix_set.items():
			logger.info("\t%s has %d actions, and %d tables" %(_name, len(self.ingress_action_set[_name]), len(self.ingress_table_set[_name])))
		logger.info(" - myDeparser: %s" %(str(self.deparser_list)))
		return

	def code_generator_main(self):
		"""
		Description: This function handles all P4 code generation process
		"""
		res_code = None
		if self.p4_version == 'p414':
			res_code = self.p414_generator_main()
		elif self.p4_version == 'p416':
			res_code = self.p416_generator_main()
		return res_code

	def p414_generator_main(self):
		"""
		Description: This function handles P4-14 code generation
		"""
		res = ""
		my_default_code = self.code_gen_handle_include()
		res += my_default_code + "\n"

		if self.macro_list != None:
			my_macro_code = self.code_gen_handle_const()
			res += my_macro_code + "\n"

		if self.header_list != None:
			my_header_code = self.code_gen_handle_header()
			res += my_header_code + "\n"

		if self.parser_state_list != None:
			my_parser_code = self.code_gen_handle_parser()
			res += my_parser_code + "\n"

		my_ingress_code = self.code_gen_handle_ingress_p414()
		res += my_ingress_code + "\n"
		my_egress_code = self.code_gen_handle_egress()
		res += my_egress_code + "\n"

		return res

	def p416_generator_main(self):
		"""
		Description: This function handles P4-16 code generation
		"""
		res = ""
		my_default_code = self.code_gen_handle_include()
		res += my_default_code + "\n"

		if self.macro_list != None:
			my_macro_code = self.code_gen_handle_const()
			res += my_macro_code + "\n"
		
		if self.header_list != None:
			my_header_code = self.code_gen_handle_header()
			res += my_header_code + "\n"
		
		if self.parser_state_list != None:
			my_parser_code = self.code_gen_handle_parser()
			res += my_parser_code + "\n"

		my_vrycksum_code = self.code_gen_handle_vrycksum()
		res += my_vrycksum_code + "\n"
		
		my_ingress_code = self.code_gen_handle_ingress()
		res += my_ingress_code + "\n"
		my_egress_code = self.code_gen_handle_egress()
		res += my_egress_code + "\n"

		my_csum_code = self.code_gen_handle_csum()
		res += my_csum_code + "\n"

		if self.deparser_header_list != None:
			my_deparser_code = self.code_gen_handle_deparser()
			res += my_deparser_code + "\n"

		my_main_code = self.code_gen_handle_main()
		res += my_main_code + "\n"
		return res

	def code_gen_handle_include(self):
		"""
		Input: None
		Output: P4 code
		"""
		const_code = ""
		if self.p4_version == 'p414':
			const_code += "/* -*_ p4_14 -*- */\n"
			const_code += "#include <tofino/intrinsic_metadata.p4>\n"
			const_code += "#include <tofino/constants.p4>\n"
		elif self.p4_version == 'p416':
			const_code += "/* -*- P4_16 -*- */\n"
			const_code += "#include <core.p4>\n"
			const_code += "#include <v1model.p4>\n"		
		return const_code

	def code_gen_handle_const(self):
		"""
		Input: self.header_list
		Output: P4 code
		"""
		cp = header.const_var_parser(self.macro_list, self.const_list)
		if self.p4_version == 'p414':
			cp.generate_p414_code()
		elif self.p4_version == 'p416':
			cp.generate_p4_code()
		return cp.p4_code

	def code_gen_handle_header(self):
		"""
		Input: final_header_list
		Output: P4 code
		"""
		hp = header.header_parser(self.header_list, self.metadata_dict)
		if self.p4_version == 'p414':
			hp.generate_p414_code()
		elif self.p4_version == 'p416':
			hp.generate_p4_code()
		return hp.p4_code

	def code_gen_handle_parser(self):
		"""
		Input: final parser_state_list
		Output: P4 code
		"""
		mpp = MyParser.myparser(self.header_list, self.parser_state_list)
		if self.p4_version == 'p414':
			mpp.generate_p414_code()
		elif self.p4_version == 'p416':
			mpp.generate_p4_code()
		return mpp.p4_code

	def code_gen_handle_vrycksum(self):
		"""
		Input: None
		Output: P4 code
		"""
		my_vrycksum = MyVerifyChecksum.my_verify_checksum()
		my_vrycksum.generate_p4_code()
		return my_vrycksum.p4_code

	def code_gen_handle_nf_selection(self, nf_node):
		"""
		Description: generate the NF selection table for the input nf_node
		Results are stored in the list 'nf_node.nf_select_table'
		Input: nf_node
		Output: None (updates in nf_node.nf_select_table)
		"""
		lib_prefix = '%s_%d_%d' %(nf_node.action_prefix, nf_node.service_path_id, nf_node.service_id)
		table_name = '%s_select_table' %(lib_prefix)
		nf_select_table = MyIngress.p4_table(None, table_name, len(nf_node.next_nf_selection)+20)
		transition_cond = []
		routing_list = []
		for flowspec_tuple in nf_node.next_nf_selection:
			(t_transition, t_spi, t_si) = flowspec_tuple
			if t_transition:
				for cond in t_transition:
					if cond not in transition_cond:
						transition_cond.append(cond)
			routing_list.append((t_spi, t_si))

		if nf_node.is_shared_module():
			transition_cond.append({'prev_spi': []})
			transition_cond.append({'prev_si': []})
		nf_node.nf_select_tables.append((nf_select_table, transition_cond, routing_list))
		return

	def code_gen_handle_selection_table(self, t_table, t_transition_cond, routing_list):
		"""
		Description: generate the NF selection table according to the input configuration
		Input: NF select table instance, routing list for all branches
		Output: str
		"""
		if len(routing_list)==0:
			return ''

		global built_in_flowspec_lookup_table_p414
		res_code = ""
		t_table_name = t_table.table_name
		t_table_action = []
		spi_miss = MyIngress.p4_action(None, "%s_miss" %(t_table_name))
		spi_miss.add_command(1, ('meta.service_path_id', 0))
		#spi_miss.add_command(1, ('meta.service_id', 0))
		spi_miss.add_command(0, ('sys_set_drop_flag', ''))
		t_table_action.append(spi_miss.action_name)
		res_code += spi_miss.generate_p414_code()

		spi_hit = [MyIngress.p4_action(None, "%s_hit_%d" %(t_table_name, i)) for i in range(len(routing_list))]
		for i, branch in enumerate(routing_list):
			spi_hit[i].add_command(1, ('meta.prev_spi', 'meta.service_path_id'))
			spi_hit[i].add_command(1, ('meta.prev_si', 'meta.service_id'))
			spi_hit[i].add_command(1, ('meta.service_path_id', branch[0]))
			spi_hit[i].add_command(1, ('meta.service_id', branch[1]))
			res_code += spi_hit[i].generate_p414_code()
			t_table_action.append(spi_hit[i].action_name)
		t_table.add_actions(t_table_action)

		if t_transition_cond==None:
			t_table.update_default_action(spi_hit[0].action_name)
		else:
			if len(t_transition_cond)==0: # t_transition_cond = []
				t_table.update_default_action(spi_hit[0].action_name)
			else:
				t_table.update_default_action(spi_miss.action_name)
		
		match_field = []
		for flow in t_transition_cond:
			flow_key = flow.keys()[0]
			flow_val = flow[flow_key]
			field = built_in_flowspec_lookup_table_p414[flow_key]
			if field not in match_field:
				if flow_key == 'prev_spi' or flow_key == 'prev_si':
					t_table.add_key(field, 'exact')
				else:
					t_table.add_key(field, 'ternary')
				match_field.append(field)
		res_code += t_table.generate_p414_code()
		return res_code

	def code_gen_handle_ingress_p414(self):
		global built_in_flowspec_lookup_table_p414
		res_code = ""
		# generate field_list and field_list_calc
		for key, val in self.field_list_set.items():
			res_code += val + '\n'
		for key, val in self.field_list_calc_set.items():
			res_code += val + '\n'

		nf_chain_count = len(self.scanner.flowspec_nfchain_mapping)
		res_code += p414_ingress_start

		# generate actions and tables
		nf_class_record = []
		for nf_name in self.action_prefix_set.keys():
			res_code += "/* Code from %s */\n" %(nf_name)
			action_prefix = self.action_prefix_set[nf_name]
			table_prefix = self.table_prefix_set[nf_name]
			my_ingress = MyIngress.ingress_match_action(action_prefix, None, \
				self.ingress_action_set[nf_name], None, None, None)
			my_ingress.generate_p414_action_code()
			# do not add duplicate NF actions
			if self.nf_lookup_table[nf_name] not in nf_class_record:
				res_code += my_ingress.p4_action_code
				nf_class_record.append(self.nf_lookup_table[nf_name])
			my_ingress = MyIngress.ingress_match_action(action_prefix, \
				table_prefix, self.ingress_action_set[nf_name], \
				self.ingress_table_set[nf_name], None, None)
			my_ingress.generate_p414_table_code()
			res_code += my_ingress.p4_table_code

		res_code += '\t/* sys actions/tables */\n'
		spi_table = MyIngress.p4_table(None, 'spi_select_table')
		t_transition_cond = []
		routing_list = []

		global_graph = convert_global_nf_graph(self.scanner)
		for node in global_graph.heads:
			routing_list.append((node.service_path_id, node.service_id))

		for i in range(nf_chain_count):
			nfchain = self.scanner.flowspec_nfchain_mapping.values()[i]
			nfchain_ll_node = self.scanner.struct_nlinkedlist_dict[nfchain]
			for cond in nfchain_ll_node.transition_condition:
				if cond not in t_transition_cond:
					t_transition_cond.append(cond)
		res_code += self.code_gen_handle_selection_table(spi_table, t_transition_cond, routing_list)
		res_code += '\n'

		for node in self.p4_list:
			self.code_gen_handle_nf_selection(node)
			select_table, t_transition_cond, routing_list = node.nf_select_tables[0]
			res_code += self.code_gen_handle_selection_table(select_table, t_transition_cond, routing_list)
		
		sys_init_metadata = MyIngress.p4_action(None, "sys_init_metadata", True)
		#sys_init_metadata.add_command(1, ("meta.service_path_id", "0"))
		#sys_init_metadata.add_command(1, ("meta.service_id", "1"))
		sys_init_metadata.add_command(1, ("meta.forward_flag", "0"))
		sys_init_metadata.add_command(1, ("meta.controller_flag", "0"))
		sys_init_metadata.add_command(1, ("meta.nsh_flag", "0"))
		#sys_init_metadata.add_command(1, ("meta.drop_flag", "0"))
		res_code += sys_init_metadata.generate_p414_code()

		res_code += "control ingress {\n"
		res_code += '%s\n' %(sys_init_metadata.generate_apply_p414_code())
		res_code += p414_preprocess_nsh
		res_code += '\telse {\n'
		if nf_chain_count>0:
			res_code += spi_table.generate_apply_p414_code()
		res_code += '\t}\n\n'


		# Segment P4 node list for each service path. Here are several rules to follow:
		# (1) entry node: first node in a chain; a node whose prev_node_list contains a BESS node.
		# (2) new subchains: first node in a subchain; first node in the merged/shared subchain.
		cf_node_list = []
		cf_graph = control_flow_graph()
		spi_p4_nodes = collections.OrderedDict()
		spi_nsh_nodes = []
		curr_spi = 0
		curr_si = 0
		prev_si = -1
		prev_shared = False
		for node in self.p4_list[1:]:
			#print('Debug info: %s[spi:%d,si:%d,t:%d,layer:%d] shared list:' %(node.name, node.service_path_id, node.service_id, node.finish_time, node.control_flow_layer), node.shared_spi_list, prev_shared)
			routing_info = (curr_spi, curr_si)
			if node.nf_class=='NSHEncap':
				spi_nsh_nodes.append(node)
				continue
			if (node.service_path_id != curr_spi) or (node.is_shared_module()) or (prev_shared and not node.is_shared_module()):
				# a possible SPI change event when traversing the graph (a new change / a shared module)
				curr_spi = node.service_path_id
				curr_si = node.service_id
				spi_p4_nodes[(curr_spi, curr_si)] = []
				prev_si = -1
				prev_shared = False
				if node.is_shared_module():
					prev_shared = True
			if node.service_id != prev_si+1: # start a new si segment (it requires one si matching)
				spi_p4_nodes[(curr_spi, curr_si)].append([node])
				# create a new control_flow_node
				tmp_si = curr_si
				curr_si = node.service_id
				cf_node = control_flow_node((curr_spi, curr_si))
				cf_node.add_nf_node(node)
				cf_graph.add_cf_node(cf_node)
				cf_node_list.append(cf_node)
				curr_si = tmp_si
			else: # keep in the last segment
				spi_p4_nodes[(curr_spi, curr_si)][-1].append(node)
				cf_node.add_nf_node(node)
			prev_si = node.service_id

		all_cf_nodes = cf_graph.get_cf_node_list()

		# generate P4 NF code with control flow graph
		layer_stack = []
		curr_spi_code = ''
		curr_nf_code = ''
		for cf_node in all_cf_nodes:
			curr_spi_code = ''
			# generate code for the current cf_node
			#print(cf_node, '- nf cnt: %d, layer: %d, index: %f, shared count: %d;' %(len(cf_node.nf_node_list), cf_node.control_flow_layer, cf_node.control_flow_idx, len(cf_node.shared_node_list)), cf_node.ancestors)
			
			curr_layer = cf_node.control_flow_layer
			while (len(layer_stack)>0):
				if curr_layer <= layer_stack[-1]:
					layer_stack.pop()
					curr_spi_code += '\t'*curr_layer+'}\n'
				else:
					break
			curr_spi_code += cf_node.get_routing_info()

			for nf_node in cf_node.nf_node_list:
				curr_nf_code = '\t/* %s */\n' %(nf_node.name)
				action_prefix = self.action_prefix_set[nf_node.name]
				table_prefix = '%s_%d_%d' %(self.action_prefix_set[nf_node.name], nf_node.service_path_id, nf_node.service_id)
				my_ingress = MyIngress.ingress_match_action(action_prefix, table_prefix, \
					self.ingress_action_set[nf_node.name], \
					self.ingress_table_set[nf_node.name], \
					self.ingress_apply_rule[nf_node.name], None)
				my_ingress.generate_p414_apply_rule_code()
				curr_nf_code += my_ingress.p4_apply_code
				curr_nf_code += '\t/* End %s */\n' %(nf_node.name)
				curr_spi_code += curr_nf_code

			# Add NF selection when it is a P4 NF module and is placed at the end of a chain
			if len(nf_node.next_nf_selection)>=1:
				for nf_select_tuple in nf_node.nf_select_tables:
					nf_select_table = nf_select_tuple[0]
					if nf_select_table != None:
						curr_spi_code += nf_select_table.generate_apply_p414_code()
			
			layer_stack.append(curr_layer)
			res_code += curr_spi_code

		while len(layer_stack) != 0:
			curr_layer = layer_stack.pop()
			res_code += '\t'*curr_layer+'}\n'
		res_code += '\n'

		'''
		# generate P4 NF code (Use stack to simulate the recursive branching)
		layer_stack = []
		curr_spi_code = ''
		curr_nf_code = ''
		for (spi_val,si_val), spi_node_list in spi_p4_nodes.items():
			# spi_start = the first P4 node of a chain
			spi_starter = spi_node_list[0][0]

			curr_spi_code = ''
			curr_layer = spi_starter.control_flow_layer
			if len(layer_stack)>0:
				if curr_layer<=layer_stack[-1]:
					layer_stack.pop()
					curr_spi_code += '\t'*(curr_layer+1)+'}\n'
			curr_idx = spi_starter.control_flow_idx
			curr_spi_code += '\t'*(curr_layer+1)
			if curr_idx == 0:
				curr_spi_code += 'if (meta.service_path_id==%d) {\n' %(spi_val)
			elif curr_idx == 1:
				curr_spi_code += 'else if (meta.service_path_id==%d) {\n' %(spi_val)
			else:
				curr_spi_code += 'else {\n'

			# We process all segments in one spi
			routing_required = False
			prev_si = -1
			for seg_node_list in spi_node_list:
				multi_seg = bool((len(spi_node_list) > 1))
				bess_skip = bool(spi_starter.service_id != 1)
				routing_required = multi_seg or bess_skip
				if routing_required:
					curr_spi_code += '\tif (meta.service_id==%d) {\n' %(seg_node_list[0].service_id)
				# generate NF code
				for node in seg_node_list:
					curr_nf_code = '\t/* %s */\n' %(node.name)
					action_prefix = self.action_prefix_set[node.name]
					if node.service_path_id == 0:
						table_prefix = self.action_prefix_set[node.name]
					else:
						table_prefix = '%s_%d_%d' %(self.action_prefix_set[node.name], node.service_path_id, node.service_id)
					my_ingress = MyIngress.ingress_match_action(action_prefix, table_prefix, \
						self.ingress_action_set[node.name], \
						self.ingress_table_set[node.name], \
						self.ingress_apply_rule[node.name], None)
					my_ingress.generate_p414_apply_rule_code()
					curr_nf_code += my_ingress.p4_apply_code
					curr_nf_code += '\t/* End %s */\n' %(node.name)
					curr_spi_code += curr_nf_code

				# Add NF selection when it is a P4 NF module and is placed at the end of a chain
				if ('nsh_%d_%d' %(node.service_path_id,node.service_id))!=node.name and len(node.next_nf_selection)>=1:
					for nf_select_tuple in node.nf_select_tables:
						nf_select_table = nf_select_tuple[0]
						if nf_select_table != None:
							curr_spi_code += nf_select_table.generate_apply_p414_code()
				if routing_required:
					curr_spi_code += '\t}\n'
			# end one segment (loop-back)
			layer_stack.append(curr_layer)
			res_code += curr_spi_code

		while len(layer_stack) != 0:
			curr_layer = layer_stack.pop()
			res_code += '\t'*(curr_layer+1)+'}\n'
		res_code += '\n'
		'''

		# handle BESS NF
		if len(spi_nsh_nodes) > 0:
			node = spi_nsh_nodes[0]
			action_prefix = self.action_prefix_set[node.name]
			table_prefix = '%s_%d_%d' %(self.action_prefix_set[node.name], node.service_path_id, node.service_id)
			my_ingress = MyIngress.ingress_match_action(action_prefix, table_prefix, \
					self.ingress_action_set[node.name], \
					self.ingress_table_set[node.name], \
					self.ingress_apply_rule[node.name], None)
			my_ingress.generate_p414_apply_rule_code()
			tmp_table_code = my_ingress.p4_apply_code
			# unrolling the loop (there are at most 4 pairs in each round)
			pair_cnt, total_pair_cnt = 0, len(spi_nsh_nodes)
			while pair_cnt < total_pair_cnt:
				tmp_pair_list = []
				for i in range(4):
					if pair_cnt < total_pair_cnt:
						tmp_pair_list.append('(meta.service_path_id==%d and meta.service_id==%d)' %(spi_nsh_nodes[pair_cnt].service_path_id, spi_nsh_nodes[pair_cnt].service_id))
					pair_cnt += 1
				
				res_code += '\tif (' if pair_cnt<=4 else '\telse if ('
				res_code += ' or '.join(tmp_pair_list) + ') {\n'
				res_code += '\t%s' %(tmp_table_code)
				res_code += '\t}\n'
		
		res_code += '\n'
		res_code += p414_packet_destine
		res_code += '} // end control\n'

		return res_code


	def code_gen_handle_ingress(self):
		"""
		Input: None
		Output: P4 code - Str
		"""
		global built_in_flowspec_lookup_table

		nf_chain_count = len(self.scanner.flowspec_nfchain_mapping)
		res_code = "\n"

		# add actions and tables for each nf_node
		for nf_name in self.action_prefix_set.keys():
			res_code += "/* Code from %s */\n" %( nf_name )
			action_prefix = self.action_prefix_set[nf_name]
			table_prefix = self.table_prefix_set[nf_name]
			my_ingress = MyIngress.ingress_match_action(action_prefix, None, \
				self.ingress_action_set[nf_name], None, None, None)
			my_ingress.generate_p4_action_code()
			res_code += my_ingress.p4_action_code

			my_ingress = MyIngress.ingress_match_action(action_prefix, \
				table_prefix, self.ingress_action_set[nf_name], \
				self.ingress_table_set[nf_name], None, None)
			my_ingress.generate_p4_table_code()
			res_code += my_ingress.p4_table_code
			res_code += "\n"
		# return res_code # Test action and table generation

		# Use p4_table class to generate "network_service_path_selector_table_(spi_num)"
		# For each NF chain graph, we place one NSP selector table.
		spi_tables = [MyIngress.p4_table(None, "network_service_path_selector_table_%d" %(i+1), 10) for i in range(nf_chain_count)]

		for i, curr_table in enumerate(spi_tables):
			nfchain = self.scanner.flowspec_nfchain_mapping.values()[i]
			nfchain_ll_node = self.scanner.struct_nlinkedlist_dict[nfchain]
			#print nfchain_ll_node.transition_condition

			curr_table_hit = MyIngress.p4_action(None, curr_table.table_name+"_hit")
			curr_table_hit.add_command(1, ("meta.service_path_id", "%d"%(i+1)))
			curr_table_miss = MyIngress.p4_action(None, curr_table.table_name+"_miss")
			res_code += curr_table_hit.generate_p4_code()
			res_code += curr_table_miss.generate_p4_code()
			curr_table.add_actions( [curr_table.table_name+"_hit", curr_table.table_name+"_miss"] )
			
			if len(nfchain_ll_node.transition_condition) == 0:
				curr_table.update_default_action(curr_table.table_name+"_hit")
			else:
				curr_table.update_default_action(curr_table.table_name+"_miss")
			
			for flowspec in nfchain_ll_node.transition_condition:
				field = built_in_flowspec_lookup_table[flowspec.keys()[0]]
				curr_table.add_key(field, "exact")
			res_code += "/* %s */\n" %(nfchain)
			res_code += curr_table.generate_p4_code()
			res_code += "\n"
		#return res_code # Test nsp_selector_table

		# Add default actions, i.e. init_metadata() (or system_init_metadata)
		sys_init_metadata = MyIngress.p4_action(None, "sys_init_metadata")
		sys_init_metadata.add_command(1, ("meta.service_path_id", "(bit<24>)1"))
		sys_init_metadata.add_command(1, ("meta.service_id", "(bit<8>)1"))
		sys_init_metadata.add_command(1, ("meta.forward_flag", "(bit<4>)0"))
		sys_init_metadata.add_command(1, ("meta.controller_flag", "(bit<4>)0"))
		sys_init_metadata.add_command(1, ("meta.nsh_flag", "(bit<4>)0"))
		sys_init_metadata.add_command(1, ("meta.drop_flag", "(bit<4>)0"))
		res_code += sys_init_metadata.generate_p4_code()

		res_code += "/* Apply Logic starts */\n"
		res_code += "apply {\n\n"
		
		res_code += "\t%s\n" %(sys_init_metadata.generate_apply_p4_code())


		# add the nfcp_nsh_remove code if there is any NSHEncap module
		# Note: if there is any NSHEncap node in the whole NF chain, then
		# we should add this piece of code to remove NSH header from the bounced packet
		if True:
			nsh_preprocess_code = ""
			nsh_preprocess_code += "\tif ( hdr.nsh.isValid() ) {\n"
			nsh_preprocess_code += "\t\tnshencap_remove_nsh_header();\n"
			nsh_preprocess_code += "\t}\n"
			res_code += nsh_preprocess_code

		# generate nf path selector code
		res_code += "\telse{\n"
		res_code += "\t\t/* select the network service path */\n\n"
		for i, curr_table in enumerate(spi_tables):
			res_code += curr_table.generate_apply_p4_code()
			res_code += "\n"
		res_code += "\t} // END else\n\n"

		# Generate the code for packet processing pipeline
		curr_service_path_id = 0
		curr_service_id = 1
		curr_code = ""
		for node in self.p4_list:
			curr_code = ""
			if node.service_path_id != curr_service_path_id:
				if curr_service_path_id != 0:
					res_code += "\t}\n\telse "
				else:
					res_code += "\t"
				curr_service_path_id = node.service_path_id
				res_code += "if ( meta.service_path_id == %d ) {\n\n" %(node.service_path_id)
			
			curr_code += "\t\tif ( meta.service_id == %d ) {\n\n" %(node.service_id)
			curr_code += "\t\t/* Code from %s */\n\n" %( node.name )
			my_ingress = MyIngress.ingress_match_action(self.action_prefix_set[node.name], 
				self.action_prefix_set[node.name]+"_%d_%d"%(node.service_path_id, node.service_id), \
				self.ingress_action_set[node.name], \
				self.ingress_table_set[node.name], \
				self.ingress_apply_rule[node.name], None)
			my_ingress.generate_p4_apply_rule_code()
			curr_code += my_ingress.p4_apply_code
			curr_code += "\n\t\t\tif ((meta.controller_flag == 1) || (meta.nsh_flag == 1)) {\n"
			# set up the self.service_path_id to skip the following NFs in the NF service chain
			curr_code += "\t\t\t\tnshencap_valid_nsh_header();\n"
			curr_code += "\t\t\t\tnshencap_setup_nsh_header();\n"
			curr_code += "\t\t\t\tmeta.service_id = %d;\n" %( 0 )
			curr_code += "\t\t\t}\n"
			curr_code += "\t\t\telse {\n"
			# otherwise, we go to the next NF in the NF service chain
			curr_code += "\t\t\t\tmeta.service_id = %d;\n" %(node.service_id+1)
			curr_code += "\t\t\t}\n"
			curr_code += "\t\t}\n"
			res_code += curr_code
		res_code += "\t}\n" # END service path ID selector
		res_code += "\telse{\n"
		res_code += "\t\t// Unexpected Traffic is dropped\n"
		res_code += "\t\tmeta.drop_flag = 1;\n"
		res_code += "\t}\n\n"

		# add the code to set up egress_spec
		res_code += "\tif (meta.nsh_flag == 1) {\n"
		if True: # default_nsh
			res_code += "\t\tnshencap_send_to_bess();\n"
		res_code += "\t}\n\n"
		
		res_code += "\tif (meta.controller_flag == 1) {\n"
		res_code += "\t\tnshencap_send_to_controller();\n"
		res_code += "\t}\n\n"

		res_code += "\tif (meta.drop_flag == 1) {\n"
		res_code += "\t\tmark_to_drop();\n"
		res_code += "\t}\n"
		res_code += "} // END Apply\n"

		# generate the default P4 code for myIngress(...){...}
		my_ingress_helper = MyIngress.ingress_match_action(None, None, None, None, None, res_code)
		my_ingress_helper.generate_p4_default_code()
		res_code = my_ingress_helper.p4_code

		return res_code

	def code_gen_handle_egress(self):
		"""
		Input: None
		Output: P4 code
		"""
		res_code = p414_egress_start
		egress = MyEgress.egress_match_action()
		if self.p4_version == 'p414':
			egress.generate_p414_code()
		elif self.p4_version == 'p416':
			egress.generate_p4_code()
		res_code += egress.p4_code
		return res_code

	def code_gen_handle_csum(self):
		"""
		Input: None
		Output: P4 code
		"""
		my_cksum = MyComCheckSum.my_compute_checksum()
		my_cksum.generate_p4_code()
		return my_cksum.p4_code

	def code_gen_handle_deparser(self):
		"""
		Input: final deparser_header_list
		Output: P4 code
		"""
		mdp = MyDeparser.mydeparser(self.header_list, self.deparser_header_list)
		mdp.generate_p4_code()
		return mdp.p4_code

	def code_gen_handle_main(self):
		"""
		Input: None
		Output: P4 code
		"""
		my_main = MySwitchMain.v1_switch_main()
		my_main.generate_p4_code()
		return my_main.p4_code


def nfcp_code_generator_tester():
	# MyHeader()
	print("NFCP Code Generator is running...\n")
	print("-----   Header   -----")
	header_list = ['Ethernet', 'IPv4', 'TCP', 'UDP']
	metadata_dict = collections.OrderedDict()
	metadata_dict['cpu_copy'] = 'bit<8>'
	metadata_dict['dip_pool_version'] = 'bit<32>'

	return


if __name__ == '__main__':
	nfcp_code_generator_tester()


