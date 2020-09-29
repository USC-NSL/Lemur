"""
*
* This script parses the Lemur user-level configuration file.
*
"""

from __future__ import print_function
import sys
import subprocess
import copy
from antlr4 import *
from LemurUserParser import LemurUserParser
from LemurUserListener import LemurUserListener

global spi_val, si_val

spi_val = 0
si_val = 0


class nf_chain_graph(object):
	def __init__(self):
		self.module_list = {}
		self.module_num = 0
		# self.heads contains all nodes that does not have parent nodes
		# self.tails contains all nodes that does not have child nodes
		self.heads = []
		self.tails = []

	def add_module(self, nf_node):
		module_key = nf_node.name
		self.module_list[module_key] = nf_node
		self.module_num += 1
		return

	def get_module(self, module_key):
		if module_key in self.module_list.keys():
			return self.module_list[module_key]
		else:
			return None

	def add_edge(self, src, dst):
		# type(src), type(dst) == nf_node
		if src.name not in self.module_list:
			self.add_module(src)
			self.heads.append(src)
			self.tails.append(src)
		else:
			src = self.module_list[src.name]
		if dst.name not in self.module_list:
			self.add_module(dst)
			self.heads.append(dst)
			self.tails.append(dst)
		else:
			dst = self.module_list[dst.name]
		if dst in src.adj_nodes:
			return

		if src in self.tails: # src is a new parent
			self.tails.remove(src)
		if dst in self.heads: # dst is a new child
			self.heads.remove(dst)
		
		self.module_list[src.name].add_neighbor(dst)
		return

	def __contains__(self, target_key):
		return (target_key in self.module_list)

	def list_modules(self):
		return self.module_list.values()

	def __iter__(self):
		return iter(self.module_list.values())


def convert_nf_graph(ll_node):
	"""
	convert_nf_graph:
	This function converts a ll_node graph into a tmp_nf_node graph 
	(a complete graph).
	(It is good to use a special definition of NF nodes, instead of ll_node)
	"""
	res_graph = nf_chain_graph()
	# the elem to iterate through the linked list
	curr_ll_node = ll_node
	next_ll_node = ll_node.next
	new_node_list = None
	prev_node_list = None

	if next_ll_node == None:
		node_c = tmp_nf_node(curr_ll_node)
		res_graph.add_module(node_c)
		res_graph.heads.append(node_c)
		res_graph.tails.append(node_c)

	while next_ll_node != None:
		# curr_ll_node and next_ll_node are non-empty node
		if len(curr_ll_node.branch) == 0 and len(next_ll_node.branch) == 0:
			# 1. curr: non-branch, next: non_branch
			node_c = tmp_nf_node(curr_ll_node)
			node_n = tmp_nf_node(next_ll_node)
			res_graph.add_edge(node_c, node_n)
		elif len(curr_ll_node.branch) == 0 and len(next_ll_node.branch) != 0:
			# 2. curr: non-branch, next: branch
			print("curr:", curr_ll_node, "n")
			node_c = tmp_nf_node(curr_ll_node)
			tmp_tail = []
			branch_idx = 0
			for curr_branch in next_ll_node.branch:
				branch_idx += 1
				# for each branch, we get the sub-grahn
				curr_branch_graph = convert_nf_graph(curr_branch)
				tmp_tail += curr_branch_graph.tails
				# merge the two graphs
				for node in curr_branch_graph.list_modules():
					# process each node in the subchain graph
					if len(node.adj_nodes) != 0:
						print("Branch %d: [%s]->[%s]" %(branch_idx, node.name, node.adj_nodes[0].name))
					res_graph.add_module(node)
				
				for head_node in curr_branch_graph.heads:
					# We create a link from the res_graph's tail to the branch's head node
					print("Branch %d: head node [%s]" %(branch_idx, head_node.name))
					res_graph.add_edge(node_c, head_node)
			res_graph.tails = tmp_tail
		elif len(curr_ll_node.branch) != 0 and len(next_ll_node.branch) == 0:
			# 3. curr: branch, next: non-branch
			print("curr:", curr_ll_node, "c")
			node_n = tmp_nf_node(next_ll_node)
			res_graph.add_module(node_n)
			for tail_node in res_graph.tails:
				tail_node.add_neighbor(node_n)
			res_graph.tails = [node_n]
		else:
			pass
		curr_ll_node = next_ll_node
		next_ll_node = next_ll_node.next
	return res_graph


class linkedlist_node(object):
	def __init__(self):
		# instance = str, var, nlist
		# transition_condition = ntuple
		# branch = list of network service paths (root nodes of each path)
		# length = the length for the current node
		# prev = prev node
		# next = next node
		self.instance = None
		self.spi = 0
		self.si = 0
		self.transition_condition = None
		self.branch = []
		self.length = 0
		self.prev = None
		self.next = None

	def set_node_instance(self, node_instance, scanner):
		self.instance = copy.deepcopy(node_instance)
		self.postprocess_branches(scanner)

	def set_transition_condition(self, ntuple_instance):
		self.transition_condition = ntuple_instance

	def __len__(self):
		"""
		This function shall return the maximum length of the WHOLE NF chain
		that starts from the current node.
		"""
		len_count = 0
		curr_node = self
		while curr_node != None:
			len_count += self.length
			curr_node = curr_node.next
		return len_count

	def postprocess_branches(self, scanner):
		# scanner.struct_nlinkedlist_dict:
		# It stores all NF chains. All chains are indexed by its instance's name.
		if isinstance(self.instance, list):
			# branch node 
			# (Note: self.branch has not been setup yet, i.e. len(self.branch)==0)
			curr_branch_length, max_branch_length = 0, 0
			for subchain in self.instance:
				print("subchain:", subchain['nfchain'], " flowspec:", subchain['flowspec'])
				# note: subchain can be var, nlinkedlist
				if isinstance(subchain['nfchain'], str):
					subchain_name = subchain['nfchain']
					if subchain_name in scanner.struct_nlinkedlist_dict:
						# subchain is a chain instance
						self.branch.append(scanner.struct_nlinkedlist_dict[subchain_name])
						curr_branch_length = scanner.struct_nlinkedlist_dict[subchain_name].get_length()
					else:
						# subchain is a single NF
						new_node = linkedlist_node()
						new_node.set_node_instance(subchain_name, scanner)
						self.branch.append(new_node)
						curr_branch_length = 1
					#print("str", scanner.struct_nlinkedlist_dict[subchain_name])
				elif isinstance(subchain['nfchain'], linkedlist_node):
					# subchain is a NF chain definition
					self.branch.append( subchain['nfchain'] )
					curr_branch_length = subchain['nfchain'].get_length()
				max_branch_length = max(max_branch_length, curr_branch_length)
		else:
			# normal NF node
			self.length = 1
		return

	def get_nf_node(self):
		"""
		get_nf_graph(self):
		This function will return a list. It can convert the linkedlist, starting
		from the self node. 
		Note: the graph struct comes from the 'branch' nodes. Otherwise, the result 
		list only contains one node.
		"""
		res_node_list = []
		if len(self.branch) == 0:
			# process a non-branch node
			new_node = tmp_nf_node()
			new_node.setup(self)
			res_node_list.append([new_node])
		else:
			# process a branch node
			for curr_branch in self.branch:
				tmp_list = []
				curr_node = curr_branch
				while curr_node != None:
					if len(curr_node.branch) == 0:
						# process a non-branch node
						new_node = tmp_nf_node()
						new_node.setup(curr_node)
						tmp_list.append(new_node)
					else:
						# process a branch node
						tmp_list = curr_node.get_nf_graph_branch()
					res_node_list.append(tmp_list)
					curr_node = curr_node.next
		return res_node_list

	def get_nf_graph_branch(self):
		"""
		Helper function:
		process the ll->graph convertion for any 'branch' nodes
		"""
		return None

	def get_length(self):
		return len(self)

	def get_all_nodes(self):
		res_nodes = []
		curr_node = self
		while curr_node != None:
			if len(curr_node.branch) == 0:
				# process normal node
				res_nodes.append(curr_node)
			else:
				# process 'branch' node
				res_nodes += curr_node.get_all_nodes_branch()

			curr_node = curr_node.next
		return res_nodes

	def get_all_nodes_branch(self):
		"""
		Helper function: (get_all_nodes)
		"""
		res_nodes = []
		for bb in self.branch:
			curr_node = bb
			while curr_node != None:
				if len(curr_node.branch) == 0:
					# process normal node
					res_nodes.append(curr_node)
				else:
					# a branch inside a branch
					res_nodes += curr_node.get_all_nodes_branch()
				curr_node = curr_node.next
		return res_nodes

	def _draw_pipeline(self, graph_args=None):
		"""
		print_pipeline:
		Print the whole pipeline.
		1. start with a linear NF chain, which does not have any branch
		2. handle the branch struct
		"""
		# generate the NF placement graph (in the output format)
		if graph_args is None:
			graph_args = []

		nf_graph = convert_nf_graph(self)
		modules = nf_graph.list_modules()
		print("Draw Pipeline - %d modules" %(len(modules)))
		names = []
		node_labels = {}

		for m in modules:
			# all NF modules in the NF chain graph
			print('NF: %s, spi: %d, si: %d' %(m.name, m.spi, m.si))
			name = m.name
			mclass = m.nf_class
			names.append(name)
			node_labels[name] = '%s\\n%s' %(name, mclass)
			node_labels[name] += 'spi:%d si:%d' %(m.spi, m.si)

		try:
			f = subprocess.Popen('graph-easy ' + ' '.join(graph_args), shell=True,\
				stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE )

			for name in names:
				for next_node in nf_graph.module_list[name].adj_nodes:
					next_nf_name = next_node.name
					print('[%s] -> [%s]' %(name, next_nf_name))
					print('[%s] -> [%s]' %(node_labels[name], node_labels[next_nf_name]), file=f.stdin )
			output, error = f.communicate()
			f.wait()
			return output

		except IOError as e:
			if e.errno == errno.EPIPE:
				raise cli.CommandError('"graph-easy" program is not available')
			else:
				raise

	def __str__(self):
		"""
		 __str__:
		The simple printer function. Note: the function does NOT print the details
		for the 'branch' node.
		To use this function, write 'self.__str__()' or 'print self'.
		"""
		res_str = ""
		if len(self.branch) != 0:
			res_str += 'NF Branch[spi=%d]' %(self.spi)
		else:
			res_str += "%s[spi=%d si=%d]" %(self.instance, self.spi, self.si)
		
		if self.next != None:
			res_str += " -> " + self.next.__str__()
		return res_str

	# The next three functions are used to assign SPI and SI values for
	# all NFs in the current chain
	def assign_service_index(self):
		"""
		assign_service_index can assign and update the spi_val and si_val.
		Therefore, achieve the first step for NF placement - assigning SPI
		and SI values for each NF.
		"""
		global spi_val, si_val
		if len(self.branch) != 0:
			# branch node
			self.update_service_index_nextfunc()
			for subchain in self.branch:
				# each subchain is a nll_node (i.e. the root node of the subchain)
				self.update_service_index_nextchain()
				subchain.assign_service_index()
			# set up the spi_val and si_val for the rest of netchain
			if self.next != None:
				self.update_service_index_nextchain()
				self.next.assign_service_index()
		else:
			# normal NF node
			self.update_service_index_nextfunc()
			if self.next != None:
				self.next.assign_service_index()
		return

	def update_service_index_nextfunc(self):
		"""
		update_service_index_nextfunc:
		It should update si_val by 1. Also, it sets up the self.spi and self.si
		"""
		global spi_val, si_val
		si_val += 1
		self.spi = spi_val
		self.si = si_val
		return
		
	def update_service_index_nextchain(self):
		"""
		update_service_index_nextchain:
		It should restart spi_val and si_val for a new chain.
		"""
		global spi_val, si_val
		spi_val += 1
		si_val = 0
		return


class UDLemurUserListener(LemurUserListener):
	def __init__(self):
		# Lookup Table for basic data types
		self.var_int_dict = {}
		self.var_float_dict = {}
		self.var_string_dict = {}
		self.var_bool_dict = {}
		self.func_dict = {}

		self.struct_ntuple_dict = {}
		self.struct_nlist_dict = {}
		self.struct_nlinkedlist_dict = {}
		self.struct_graph_dict = {}

		# flowspec_nfchain_mapping stores the nfchain configuration
		# i.e. flowspec : NF chain
		self.flowspec_nfchain_mapping = {}

		self.overall_nf_chain_list = []
		self.service_path_count = 0
		self.line_count = 0
		return

	# Enter a parse tree produced by LemurUserParser#total.
	def enterTotal(self, ctx):
		print("Lemur AST Walker starts:")
		pass

	# Exit a parse tree produced by LemurUserParser#total.
	def exitTotal(self, ctx):
		print("Lemur AST Walker ends!")
		pass


	# Enter a parse tree produced by LemurUserParser#line.
	def enterLine(self, ctx):
		self.line_count += 1
		pass

	# Exit a parse tree produced by LemurUserParser#line.
	def exitLine(self, ctx):
		pass

	# Enter a parse tree produced by LemurUserParser#define_int.
	def enterDefine_int(self, ctx):
		#print(ctx.VARIABLENAME(), ctx.INT(), type(str(ctx.INT())))
		var_name = str(ctx.VARIABLENAME())
		var_value = int(str(ctx.INT()))
		self.var_int_dict[var_name] = var_value
		pass

	# Exit a parse tree produced by LemurUserParser#define_int.
	def exitDefine_int(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#define_float.
	def enterDefine_float(self, ctx):
		#print(ctx.VARIABLENAME(), ctx.FLOAT(), type(str(ctx.FLOAT())))
		var_name = str(ctx.VARIABLENAME())
		var_value = float(str(ctx.FLOAT()))
		self.var_float_dict[var_name] = var_value
		pass

	# Exit a parse tree produced by LemurUserParser#define_float.
	def exitDefine_float(self, ctx):
		pass

	def get_string_from_ctx(self, ctx, idx=None):
		if idx == None:
			res = str(ctx.STRING())[1:-1]
		else:
			res = str(ctx.STRING(idx))[1:-1]
		return res

	# Enter a parse tree produced by LemurUserParser#define_string.
	def enterDefine_string(self, ctx):
		var_name = str(ctx.VARIABLENAME())
		var_value = self.get_string_from_ctx(ctx)
		self.var_string_dict[var_name] = var_value
		pass

	# Exit a parse tree produced by LemurUserParser#define_string.
	def exitDefine_string(self, ctx):
		pass


	def get_bool_from_ctx(self, ctx):
		res = None
		bool_value = str(ctx.BOOL())
		if bool_value == 'False':
			res = False
		elif bool_value == 'True':
			res = True
		return res

	# Enter a parse tree produced by LemurUserParser#define_bool.
	def enterDefine_bool(self, ctx):
		var_name = str(ctx.VARIABLENAME())
		var_value = self.get_bool_from_ctx(ctx)
		self.var_bool_dict[var_name] = var_value
		pass

	# Exit a parse tree produced by LemurUserParser#define_bool.
	def exitDefine_bool(self, ctx):
		pass

	def get_nf_from_ctx(self, ctx):
		# return the NF's name from the netfunction context
		res = str(ctx.VARIABLENAME())
		return res

	# Enter a parse tree produced by LemurUserParser#define_nfinstance.
	def enterDefine_nfinstance(self, ctx):
		# Note: each NF instance can be either a BESS or P4 module
		#print("Enter Define NetFunc")
		var_name = str(ctx.VARIABLENAME())
		var_value = self.get_nf_from_ctx(ctx.netfunction())
		self.func_dict[var_name] = var_value
		#print(var_name, var_value)
		pass

	# Exit a parse tree produced by LemurUserParser#define_nfinstance.
	def exitDefine_nfinstance(self, ctx):
		pass


	def get_nlistelem_from_ctx(self, nlist_elem_ctx):
		"""
		return the nlist element based on the nlist_elem object's context
		"""
		nlistelem_obj = nlist_elem_ctx
		res_value = None
		if nlistelem_obj.ntuple() != None:
			res_value = self.get_ntuple_from_ctx(nlistelem_obj.ntuple())
			#print("nlist elem(ntuple):", res_value)
		elif nlistelem_obj.INT() != None:
			res_value = int(str(nlistelem_obj.INT()))
		elif nlistelem_obj.FLOAT() != None:
			res_value = float(str(nlistelem_obj.FLOAT()))
		elif nlistelem_obj.STRING() != None:
			res_value = self.get_string_from_ctx(nlistelem_obj)
		elif nlistelem_obj.VARIABLENAME() != None:
			res_value = str(nlistelem_obj.VARIABLENAME())

		return res_value


	def get_nlist_from_ctx(self, nlist_obj):
		res_nlist = []
		nlistelem_obj_list = nlist_obj.nlist_elem()
		for nlistelem_obj in nlistelem_obj_list:
			var_value = self.get_nlistelem_from_ctx(nlistelem_obj)
			res_nlist.append(var_value)
		return res_nlist

	# Enter a parse tree produced by LemurUserParser#define_nlist.
	def enterDefine_nlist(self, ctx):
		var_name = str(ctx.VARIABLENAME())
		nlist_obj = ctx.nlist()
		nlist = self.get_nlist_from_ctx(nlist_obj)
		self.struct_nlist_dict[var_name] = nlist
		pass

	# Exit a parse tree produced by LemurUserParser#define_nlist.
	def exitDefine_nlist(self, ctx):
		pass


	def get_ntupleelem_from_ctx(self, ntuple_elem_ctx):
		"""
		return the ntuple element based on the ntuple_elem object's context
		Note: ntuple elem: {str : str/int/float/var/nlist/nlinkedlist}
		"""
		ntupleelem_obj = ntuple_elem_ctx
		res_value = None
		if ntupleelem_obj.STRING(1) != None:
			#print( str(ntupleelem_obj.STRING(1)) )
			res_value = self.get_string_from_ctx(ntupleelem_obj, 1)
		elif ntupleelem_obj.INT() != None:
			#print( int(str(ntupleelem_obj.INT())) )
			res_value = int(str(ntupleelem_obj.INT()))
		elif ntupleelem_obj.FLOAT() != None:
			#print( float(str(ntupleelem_obj.INT())) )
			res_value = float(str(ntupleelem_obj.INT()))
		elif ntupleelem_obj.VARIABLENAME() != None:
			#print( str(ntupleelem_obj.VARIABLENAME()) )
			res_value = str(ntupleelem_obj.VARIABLENAME())
		elif ntupleelem_obj.nlist() != None:
			#print("focus", self.get_nlist_from_ctx(ntupleelem_obj.nlist()) )
			res_value = self.get_nlist_from_ctx(ntupleelem_obj.nlist())
		elif ntupleelem_obj.nlinkedlist() != None:
			res_value = self.get_nlinkedlist_from_ctx(ntupleelem_obj.nlinkedlist())
		return res_value

	def get_ntuple_from_ctx(self, ntuple_obj):
		# Note: each ntuple_elem has at most two string elements.
		res_ntuple = {}
		ntupleelem_obj_list = ntuple_obj.ntuple_elem()
		for ntupleelem_obj in ntupleelem_obj_list:
			#print( str(ntupleelem_obj.STRING(0)) )
			var_name = self.get_string_from_ctx(ntupleelem_obj, 0)
			var_value = self.get_ntupleelem_from_ctx(ntupleelem_obj)
			res_ntuple[var_name] = var_value
		return res_ntuple

	# Enter a parse tree produced by LemurUserParser#define_ntuple.
	def enterDefine_ntuple(self, ctx):
		#print("Enter Define Tuple")
		var_name = str(ctx.VARIABLENAME())
		ntuple_obj = ctx.ntuple()
		ntuple = self.get_ntuple_from_ctx(ntuple_obj)
		self.struct_ntuple_dict[var_name] = ntuple
		pass

	# Exit a parse tree produced by LemurUserParser#define_ntuple.
	def exitDefine_ntuple(self, ctx):
		pass


	def get_nlinkedlistelem_from_ctx(self, nll_elem_obj):
		# Note: nlinkedlistelem can be netfunc (str), var (str), nlist (list)
		res_value = None
		if nll_elem_obj.netfunction() != None:
			#print('nll elem - netfunc:', str(nll_elem_obj.netfunction().VARIABLENAME()))
			res_value = str(nll_elem_obj.netfunction().VARIABLENAME())
		elif nll_elem_obj.VARIABLENAME() != None:
			#print('nll elem - var:', str(nll_elem_obj.VARIABLENAME()))
			res_value = str(nll_elem_obj.VARIABLENAME())
		elif nll_elem_obj.nlist() != None:
			# a 'branch' node
			#print('nll elem - nlist:', self.get_nlist_from_ctx(nll_elem_obj.nlist()))
			res_value = self.get_nlist_from_ctx(nll_elem_obj.nlist())
		return res_value

	def get_nlinkedlist_from_ctx(self, nlinkedlist_obj):
		"""
		This function will return the root node for the defined linkedlist instance.
		At this point, we don't have to further process the linkedlist.
		"""
		# root node
		root_ll_node = None
		curr_ll_node = root_ll_node
		nll_obj_list = nlinkedlist_obj.nlinkedlist_elem()
		for nll_elem_obj in nll_obj_list:
			# for each ll_elem, we create a nlinkedlist_node instance to store it.
			new_ll_node = linkedlist_node()
			# node_instance: nlist / Var / NF()
			node_instance = self.get_nlinkedlistelem_from_ctx(nll_elem_obj)
			new_ll_node.set_node_instance(node_instance, self)
			
			if root_ll_node == None: # the first node
				new_ll_node.prev = None
				root_ll_node = new_ll_node
			else: # not the first node (set up the curr_ll_node's next node)
				new_ll_node.prev = curr_ll_node
				curr_ll_node.next = new_ll_node
			curr_ll_node = new_ll_node
		return root_ll_node

	# Enter a parse tree produced by LemurUserParser#define_nlinkedlist.
	def enterDefine_nlinkedlist(self, ctx):
		"""
		Enter a new NF chain definition (a nlinkedlist)
		Update the SPI and SI values:
		SPI += 1, SI = 0
		"""
		print("Enter Define nLinkedList")
		var_name = str(ctx.VARIABLENAME())
		nlinkedlist_obj = ctx.nlinkedlist()
		nlinkedlist = self.get_nlinkedlist_from_ctx(nlinkedlist_obj)
		print("Store nlinkedlist. Name: %s, Len: %d" %(var_name, nlinkedlist.get_length()))
		self.struct_nlinkedlist_dict[var_name] = nlinkedlist
		pass

	# Exit a parse tree produced by LemurUserParser#define_nlinkedlist.
	def exitDefine_nlinkedlist(self, ctx):
		pass

	# Enter a parse tree produced by LemurUserParser#define_flowspec.
	def enterDefine_flowspec(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#define_flowspec.
	def exitDefine_flowspec(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#define_nfchain.
	def enterDefine_nfchain(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#define_nfchain.
	def exitDefine_nfchain(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#configue_nfchain.
	def enterConfig_nfchain(self, ctx):
		# When a NF chain is configured with a flowspec, we then consider
		# the placement of the NF chain (starting by assigning SPI and SI
		# values for each NF)
		global spi_val, si_val
		spi_val += 1
		si_val = 0

		self.service_path_count += 1
		print(ctx.VARIABLENAME(0), ctx.VARIABLENAME(1))
		flowspec = str(ctx.VARIABLENAME(0))
		nfchain = str(ctx.VARIABLENAME(1))
		self.struct_nlinkedlist_dict[nfchain].assign_service_index()
		self.flowspec_nfchain_mapping[flowspec] = nfchain
		print(self.struct_nlinkedlist_dict[nfchain])
		pass

	# Exit a parse tree produced by LemurUserParser#configue_nfchain.
	def exitConfig_nfchain(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#flowspec.
	def enterFlowspec(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#flowspec.
	def exitFlowspec(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#netfunction_chain.
	def enterNetfunction_chain(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#netfunction_chain.
	def exitNetfunction_chain(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#netfunction.
	def enterNetfunction(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#netfunction.
	def exitNetfunction(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#nlist.
	def enterNlist(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#nlist.
	def exitNlist(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#nlist_elem.
	def enterNlist_elem(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#nlist_elem.
	def exitNlist_elem(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#ntuple.
	def enterNtuple(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#ntuple.
	def exitNtuple(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#ntuple_elem.
	def enterNtuple_elem(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#ntuple_elem.
	def exitNtuple_elem(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#nlinkedlist.
	def enterNlinkedlist(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#nlinkedlist.
	def exitNlinkedlist(self, ctx):
		pass


	# Enter a parse tree produced by LemurUserParser#nlinkedlist_elem.
	def enterNlinkedlist_elem(self, ctx):
		pass

	# Exit a parse tree produced by LemurUserParser#nlinkedlist_elem.
	def exitNlinkedlist_elem(self, ctx):
		pass







