
"""
* Title: ingress_match_action.py
* Description:
* The script is used to parse the ingress actions/tables specification part 
* in the target file.
* In order to handle conflicts, the output code should contain a prefix.
* The prefix is the library file's name.
*
* Author: Jianfeng Wang
* Time: 01/23/2018
* Email: jianfenw@usc.edu
"""

import sys
sys.path.append('..')
import subprocess
import collections
import copy
import util.lang_parser_helper as lang_helper

def extract_keyword_from_string(input_str, i_mark):
	"""
	This will extrack the key word, which is warpped around by 'i_mark' marks.
	For example:
	Input: input_str = "  #silkroad# "; i_mark = '#'
	Output: output_str = "silkroad"
	"""
	if input_str.count(i_mark) != 2:
		return ""
	str_len = len(input_str)
	s_index = -1
	e_index = str_len
	for i in range(str_len):
		if input_str[i] == i_mark:
			s_index = i
			break
	for i in reversed(range(str_len)):
		if input_str[i] == i_mark:
			e_index = i
			break
	return input_str[s_index+1:e_index]


class p4_action(object):
	"""
	Description:
	The p4_action class is used to represent a p4 action.
	libParser can parse the library file, and create a new p4_action instance.
	codeGenerator can call p4_action_instance.generate_p4_code() to generate the P4 code
	"""
	def __init__(self, input_lib_prefix=None, input_action_name=None, has_apply_table=False):
		self.lib_prefix = ""
		if input_lib_prefix != None:
			self.lib_prefix = copy.deepcopy(input_lib_prefix)

		self.action_name = copy.deepcopy(input_action_name)
		self.cmd_set = []
		self.apply_table = p4_table(None, self.action_name+'_apply', 0)
		self.apply_table.add_actions([self.action_name])
		self.apply_table.update_default_action(self.action_name)
		self.has_apply_table = has_apply_table
		return

	def add_command(self, cmd_type, cmd):
		"""
		Description: Add a cmd to the action
		cmd_type==1 -> modify; 
		cmd_type==2 -> call another action
		"""
		self.cmd_set.append((cmd_type, cmd)) 
		return

	def generate_p4_code(self):
		res_code = "\taction %s() {\n" %(self.action_name)
		for command in self.cmd_set:
			if command[0] == 0: # call another action
				res_code += "\t\t%s(%s);\n" %(command[1][0], command[1][1])
			elif command[0] == 1: # modify header/metadata field
				res_code += "\t\t%s = %s;\n" %(command[1][0], command[1][1])
			else:
				continue
		res_code += "\t}\n\n"
		return res_code

	def generate_p414_code(self):
		res_code = "action %s() {\n" %(self.action_name)
		for cmd_type, cmd_val in self.cmd_set:
			if cmd_type == 0: # call another action
				res_code += "\t%s(%s);\n" %(cmd_val[0], cmd_val[1])
			elif cmd_type == 1: # modify header/metadata
				res_code += "\tmodify_field(%s, %s);\n" %(cmd_val[0], cmd_val[1])
			else:
				continue
		res_code += "}\n"
		if self.has_apply_table:
			res_code += self.apply_table.generate_p414_code()
			res_code += "\n"
		return res_code

	def generate_apply_p4_code(self):
		res_code = "%s();\n" %(self.action_name)
		return res_code

	def generate_apply_p414_code(self):
		res_code = self.apply_table.generate_apply_p414_code()
		return res_code


class p4_table(object):
	""" Description: p4_table class is used to represent a p4 table. It can also generate
	P4 code for the table.
	The library parser will parse the library file. 
	"""
	def __init__(self, input_lib_prefix=None, input_table_name=None, input_table_size=20):
		self.lib_prefix = ""
		if input_lib_prefix != None:
			self.lib_prefix = copy.deepcopy(input_lib_prefix)

		self.table_name = ""
		if input_table_name != None:
			self.table_name = copy.deepcopy(input_table_name)

		self.table_size = input_table_size
		self.key_set = collections.OrderedDict()
		self.action_set = []
		self.default_action_idx = -1
		self.default_action = None
		return

	def setup_from_str(self, table_str, p4_node):
		match_start = False
		self.table_size = 0
		for line in table_str.split('\n'):
			match_res = lang_helper.lib_parser_ingress_table_match_start(line)
			if match_res:
				match_start = True
				line = match_res.group(1).strip()
			if match_start:
				field_res = lang_helper.lib_parser_ingress_table_match(line)
				if field_res:
					key = field_res.group(1).strip()
					method = field_res.group(2).strip()
					self.add_key(key,method)
				if '}' in line:
					match_start = False

			default_res = lang_helper.lib_parser_ingress_table_default_action_start(line, 'p414')
			if default_res:
				default_action = default_res.group(2).strip()
				if '(' in default_action:
					idx = default_action.index('(')
					default_action = default_action[:idx]
				self.update_default_action(default_action)

			size_res = lang_helper.lib_parser_ingress_table_size(line)
			if size_res:
				size_str = size_res.group(2).strip()
				if size_str in p4_node.macro_list.keys():
					self.table_size = int(p4_node.macro_list[size_str])
				else:
					self.table_size = int(size_str)
		return

	def add_key(self, key, method):
		self.key_set[key] = method
		return

	def add_keys(self, key_dict):
		for key, val in key_dict.items():
			self.add_key(key, val)
		return

	def add_action(self, action_name):
		self.action_set.append(action_name)
		return

	def add_actions(self, action_list):
		for curr_action in action_list:
			self.add_action(curr_action)
		return

	def update_default_action(self, default_action_name):
		"""
		Description: set up the default action for the table. The default action
		must be included in the table.action_set.
		"""
		self.default_action = default_action_name
		if default_action_name not in self.action_set:
			self.default_action_idx = -1
		else:
			self.default_action_idx = self.action_set.index(default_action_name)

	def generate_p4_code(self):
		res_code = "\ttable %s {\n" %(self.table_name)

		# add keys
		res_code += "\t\tkey = {\n"
		for key, val in self.key_set.items():
			res_code += "\t\t\t%s : %s;\n" %(key, val)
		res_code += "\t\t}\n"

		# add actions
		res_code += "\t\tactions = {\n"
		for curr_action in self.action_set:
			res_code += "\t\t\t%s;\n" %(curr_action)
		res_code += "\t\t}\n"

		if len(self.action_set) >= 1:
			res_code += "\t\tdefault_action = %s();\n" %(self.action_set[self.default_action_idx])
		else:
			res_code += "\t\tdefault_action = nop;\n"
		res_code += "\t\tsize = %d;\n" %(self.table_size)
		res_code += "\t}\n"
		return res_code

	def generate_p414_code(self):
		res_code = "table %s {\n" %(self.table_name)
		# add reads
		if len(self.key_set) != 0:
			res_code += "\treads {\n"
			for key, val in self.key_set.items():
				res_code += "\t\t%s : %s;\n" %(key, val)
			res_code += "\t}\n"
		# add actions
		res_code += "\tactions {\n"
		for action in self.action_set:
			res_code += "\t\t%s;\n" %(action)
		res_code += "\t}\n"
		if self.default_action_idx != -1:
			res_code += '\tdefault_action : %s;\n' %(self.action_set[self.default_action_idx])
		res_code += '\tsize:%d;\n' %(self.table_size)
		res_code += "}\n"
		return res_code

	def generate_apply_p4_code(self):
		"""
		This function can generate the table apply code for the 'apply{...}'
		in myIngress and myEgress parts.
		"""
		res_code = "\t%s.apply();\n" %(self.table_name)
		return res_code

	def generate_apply_p414_code(self):
		"""
		Description: the function generates the table apply code for the control block
		"""
		res_code = "\tapply(%s);\n" %(self.table_name)
		return res_code

class ingress_match_action:
	'''
	Description:
	The class is used to read the P4 lib to get actions, tables, and the apply logic.
	Call 'generate_p4_code' or 'generate_p414_code' to generate code for the actions,
	tables and apply logic.
	'''
	def __init__(self, input_prefix=None, input_table_prefix=None, \
		input_action_set=None, input_table_set=None, \
		input_apply_rule=None, input_p4_code=None):

		self.output_prefix = ""
		self.table_prefix = ""
		# self.field_list_set and self.field_list_calc_set
		self.field_list_set = collections.OrderedDict()
		self.field_list_calc_set = collections.OrderedDict()

		# self.action_set and self.table_set contain all actions and tables
		self.action_set = collections.OrderedDict()
		self.table_set = collections.OrderedDict()
		self.apply_rule = collections.OrderedDict()

		self.p4_code = None
		self.p4_action_code = None
		self.p4_table_code = None
		self.p4_apply_code = None
		if input_prefix != None:
			self.output_prefix = copy.deepcopy(input_prefix)
		if input_table_prefix != None:
			self.table_prefix = copy.deepcopy(input_table_prefix)
		if input_action_set != None:
			self.action_set = copy.deepcopy(input_action_set)
		if input_table_set != None:
			self.table_set = copy.deepcopy(input_table_set)
		if input_apply_rule != None:
			self.apply_rule = copy.deepcopy(input_apply_rule)
		if input_p4_code != None:
			self.p4_code = copy.deepcopy(input_p4_code)
		return

	
	def read_default_prefix(self, filename):
		""" Description: the function reads the default prefix setting
		e.g. default_prefix = "silkroad"
		"""
		with open(filename, 'r') as fp:
			line_count = 0
			for line in fp:
				line_count += 1
				if '=' in line:
					if line.count('=') != 1:
						print "Exception: error definition, line %d" %(line_count)
						return

					parse_res = lang_helper.lib_parser_default_prefix(line)
					if parse_res:
						self.output_prefix = parse_res.group(2).strip()
						break
		return

	def read_field_operations(self, filename):
		"""
		Description: the function reads all structs including field_list and 
		field_list_calculation in a P4-14 lib.
		Please note: p4-16 does not support field_list and field_list_calculation
		"""
		tmp_str = ""
		with open(filename, 'r') as fp:
			line_count = 0
			field_operation_start = False
			cmt_start = False
			list_start = False
			list_calc_start = False
			field_list_name = ""
			field_calc_name = ""
			mark_stack = []
			for line in fp:
				line_count += 1
				if '# FIELD START' in line:
					field_operation_start = True
				if '# FIELD END' in line:
					field_operation_start = False
				if not field_operation_start:
					continue

				if '/*' in line:
					cmt_start = True
				if cmt_start:
					if '*/' in line:
						cmt_start = False
					continue

				# set field_list start
				parse_list = lang_helper.lib_parser_field_list_start(line)
				if parse_list:
					field_list_name = parse_list.group(1).strip()
					list_start = True
				if list_start:
					tmp_str += line
				else:
					# set field_list_calc start
					parse_list_calc = lang_helper.lib_parser_field_list_calc_start(line)
					if parse_list_calc:
						field_calc_name = parse_list_calc.group(1).strip()
						list_calc_start = True
					if list_calc_start:
						tmp_str += line
				# re matching ends  
				if "{" in line:
					mark_stack.append('{')
				if "}" in line:
					mark_stack.pop()
					if list_start:
						if len(mark_stack) == 0:
							list_start = False
							self.field_list_set[field_list_name] = tmp_str
							field_list_name = ""
							tmp_str = ""
						continue
					elif list_calc_start:
						if len(mark_stack) == 0:
							list_calc_start = False
							self.field_list_calc_set[field_calc_name] = tmp_str
							field_calc_name = ""
							tmp_str = ""
						continue
					else:
						exception_code = "Error: line %d" %(line_count)
						raise Exception(exception_code)
		return

	def read_ingress(self, filename):
		""" 
		Description: the function reads actions, tables, and apply logic
		for ingress control block.
		"""	
		tmp_str = ""
		with open(filename, 'r') as fp:
			line_count = 0
			ingress_start = False
			cmt_start = False
			action_start = False
			table_start = False
			apply_start = False
			action_name = ""
			table_name = ""
			mark_stack = []

			for line in fp:
				line_count += 1
				if 'Ingress' in line:
					ingress_start = True
				if not ingress_start:
					continue

				if '/*' in line:
					cmt_start = True
				if cmt_start:
					if "*/" in line:
						cmt_start = False
					continue

				# set action start
				parse_action = lang_helper.lib_parser_ingress_action_start(line)
				if parse_action:
					action_name = parse_action.group(1).strip()
					action_start = True
				if action_start:
					tmp_str += line
				else:
					# set table start
					parse_table = lang_helper.lib_parser_ingress_table_start(line)
					if parse_table:
						table_name = parse_table.group(1).strip()
						table_start = True
					if table_start:
						tmp_str += line
					else:
						# set apply start
						parse_apply = lang_helper.lib_parser_ingress_apply_start(line)
						if parse_apply:
							apply_start = True
						if apply_start:
							tmp_str += line

				if "{" in line:
					mark_stack.append('{')
				if "}" in line:
					mark_stack.pop()
					if action_start:
						if len(mark_stack) == 0:
							action_start = False
							self.action_set[action_name] = tmp_str
							action_name = ""
							tmp_str = ""
						continue
					elif table_start:
						if len(mark_stack) == 0:
							table_start = False
							self.table_set[table_name] = tmp_str
							table_name = ""
							tmp_str = ""
						continue
					elif apply_start:
						if len(mark_stack) == 0:
							apply_start = False
							self.apply_rule['ingress'] = tmp_str
							tmp_str = ""
						continue
					else:
						exception_code = "Error: line %d" %(line_count)
						raise Exception(exception_code)
		return

	def read_actions(self, filename):
		""" Description: This function reads all actions in the library file
		e.g.
		action drop() {
			mark_to_drop();
		}
		All actions will be kept in the action_set, which is a lookup table.
		In action_set, key = action's name; value = action's data structure
		"""
		tmp_str = ""
		with open(filename, 'r') as fp:
			line_count = 0

			new_ingress_start = False
			new_comment_start = False
			new_action_start = False
			new_table_start = False
			new_apply_start = False
			new_action_name = ""
			mark_stack = []

			for line in fp:
				line_count += 1
				if "Ingress" in line:
					new_ingress_start = True

				if not new_ingress_start:
					continue
				if new_apply_start:
					continue

				if "/*" in line:
					new_comment_start = True
				if new_comment_start:
					if "*/" in line:
						new_comment_start = False
					continue

				if "apply " in line:
					new_apply_start = True
					mark_stack = []

				if "table " in line:
					new_table_start = True
					mark_stack = []

				if "action " in line and (not new_table_start):
					new_action_name = ""
					s_index = line.index("action ")+7
					e_index = len(line)
					for i in range( s_index, len(line)):
						if line[i] == ' ':
							s_index += 1
							continue
						if line[i] == '(':
							e_index = i
							break

					new_action_name = line[ s_index: e_index ]
					#print new_action_name
					new_action_start = True
					mark_stack = []
 
				if new_action_start:
					tmp_str += line

				if "{" in line:
					mark_stack.append('{')

				if "}" in line:
					# if line_count == 96:
					#	print line, mark_stack, new_action_start
					mark_stack.pop()

					if new_table_start:
						if len(mark_stack) == 0:
							new_table_start = False
						continue
					elif new_apply_start:
						if len(mark_stack) == 0:
							new_apply_start = False
						continue
					elif new_action_start:
						if len(mark_stack) == 0:
							new_action_start = False
							self.action_set[ new_action_name ] = tmp_str
							new_action_name = ""
							tmp_str = ""
						continue
					else:
						exception_code = "Error: line %d" %(line_count)
						raise Exception(exception_code)
		return

	
	def read_tables(self, filename):
		""" Description: the function reads all tables in the library file
		e.g.
		// P4-16 table
		table ipv4_lpm {
        	key = {
            	hdr.ipv4.dstAddr: lpm;
        	}
        	actions = {
            	ipv4_forward;
            	drop;
            	NoAction;
        	}
        	size = 1024;
        	default_action = NoAction();
    	}
    	// P4-14 table
    	table ipv4_lpm {
        	reads {
            	ipv4.dstAddr: exact;
        	}
        	actions {
            	ipv4_forward;
            	drop;
        	}
        	default_action : drop();
        	size : 1024;
    	}
    	All tables will be kept in the table set, which is also a lookup table.
    	In table_set, key = table's name; value = table's data structure
		"""
		tmp_str = ""
		with open(filename, 'r') as fp:
			line_count = 0

			new_ingress_start = False
			new_comment_start = False
			new_table_start = False
			new_action_start = False
			new_apply_start = False
			new_table_name = ""
			mark_stack = []

			for line in fp:
				line_count += 1

				if "Ingress" in line:
					new_ingress_start = True

				if not new_ingress_start:
					continue

				if "/*" in line:
					new_comment_start = True

				if "*/" in line and new_comment_start:
					new_comment_start = False
					continue

				if "table " in line:
					new_table_name = ""
					s_index = line.index("table ")+6
					e_index = len(line)
					# print s_index, line[s_index]
					for i in range( s_index, len(line)):
						if line[i] == '{':
							e_index = i
							break
					#print s_index, line[s_index:]
					new_table_name = line[ s_index: e_index].strip()
					new_table_start = True
					mark_stack = []

				if "action " in line and (not new_table_start):
					new_action_start = True
					mark_stack = []

				if "apply " in line:
					new_apply_start = True
					mark_stack = []

				if new_table_start:
					tmp_str += line

				if "{" in line:
					mark_stack.append('{')

				if "}" in line:
					mark_stack.pop()

					if new_table_start:
						if len(mark_stack) == 0:
							new_table_start = False

							self.table_set[ new_table_name ] = tmp_str
							new_table_name = ""
							tmp_str = ""
						continue
					elif new_action_start:
						if len(mark_stack) == 0:
							new_action_start = False
						continue
					elif new_apply_start:
						if len(mark_stack) == 0:
							new_apply_start = False
						continue
					else:
						exception_code = "Error: line %d" %(line_count)
						raise Exception(exception_code)
		
		return

	def read_apply_rule(self, filename):
		"""
		This function is used to parse the ingress apply logic.
		It will spilt the apply logic into two parts, i.e. 
		(1) init_metadata()
		(2) modify packet header fields and metadata fields
		"""
		tmp_str = ""
		with open(filename, 'r') as fp:
			line_count = 0

			new_ingress_start = False
			new_comment_start = False
			new_apply_start = False
			mark_stack = []

			for line in fp:
				line_count += 1
				if "Ingress" in line:
					new_ingress_start = True
				# if ingress does not start or any comment, just skip them
				if (not new_ingress_start) or (new_comment_start):
					continue

				if "/*" in line:
					new_comment_start = True
				if "*/" in line and new_comment_start:
					new_comment_start = False
					continue

				if "action " in line:
					new_action_start = True

				if "apply " in line:
					new_apply_start = True
					mark_stack = []

				if new_apply_start:
					tmp_str += line

				if "{" in line:
					mark_stack.append('{')
					continue
				if "}" in line:
					mark_stack.pop()
					if new_apply_start:
						if len(mark_stack) == 0:
							new_apply_start = False
							self.apply_rule['ingress'] = tmp_str
							tmp_str = ""
						continue
					elif new_action_start:
						new_action_start = False
						continue
					else:
						continue

		
		for block_name, block_str in self.apply_rule.items():
			print block_name, block_str
		return

	def generate_p4_code(self):

		if self.p4_code == None:
			self.p4_code = ""

		res = ""
		self.generate_p4_action_code()
		res += "\n"
		res += self.p4_action_code

		self.generate_p4_table_code()
		res += "\n"
		res += self.p4_table_code

		res += "apply {\n"
		self.generate_p4_apply_rule_code()
		res += self.p4_apply_code
		res += "} // end apply\n\n"

		self.p4_code = res
		self.generate_p4_default_code()
		return

	def generate_p4_action_code(self):
		self.p4_action_code = ""
		action_code = None
		for action_key, action_value in self.action_set.items():
			action_code = self.preprocess_p4_action_code(action_key, action_value, 'p416')
			self.p4_action_code += action_code + "\n"
		return

	def generate_p414_action_code(self):
		self.p4_action_code = ""
		action_code = None
		for action_key, action_value in self.action_set.items():
			action_code = self.preprocess_p4_action_code(action_key, action_value, 'p414')
			self.p4_action_code += action_code + "\n"
		return

	def preprocess_p4_action_code(self, action_name, action_str, lang_version):
		""" Description: the action will preprocess an action with name 'action_name'.
		It adds 'self.output_prefix' to all actions inside the action_str.
		By now, we assume that in each line, there is at most one action call.
		"""
		res_str = ""
		# Scan each line to find if there is any action in this line
		# If yes, add self.output_prefix to the beginning of the action
		action_line_list = action_str.splitlines(True)
		for line in action_line_list:
			def_action = lang_helper.lib_parser_ingress_action_start(line)
			if def_action:
				action_name = def_action.group(1).strip()
				if action_name in self.action_set:
					line = line.replace(action_name, "%s_%s" %(self.output_prefix, action_name))
			call_action = lang_helper.lib_parser_ingress_action_call_action(line, lang_version)
			if call_action:
				action_name = call_action.group(1).strip()
				if action_name in self.action_set:
					line = line.replace(action_name, "%s_%s" %(self.output_prefix, action_name))
			res_str += line
		return res_str

	def generate_p4_table_code(self):
		self.p4_table_code = ""
		t_code = None
		for t_name, t_str in self.table_set.items():
			t_code = self.preprocess_p4_table_code(t_name, t_str, 'p416')
			self.p4_table_code += t_code
			self.p4_table_code += "\n"
		return

	def generate_p414_table_code(self):
		self.p4_table_code = ""
		t_code = None
		for t_name, t_str in self.table_set.items():
			t_code = self.preprocess_p4_table_code(t_name, t_str, 'p414')
			self.p4_table_code += t_code
			self.p4_table_code += "\n"
		return

	def preprocess_p4_table_code(self, table_name, table_str, lang_version):
		"""
		This funtion will generate the P4 code for the "table_name" table.
		Solution 1: 
		(1) split 'table_str' with '\n'; 
		(2) for the definition of a new action, add the self.output_prefix to the action
		(3) for table, add self.table_prefix to the table
		(4) output the res_code
		Solution 2:
		(1) convert a P4 table into an instance of class p4_table
		(2) call p4_table.generate_p4_code()
		"""
		res_str = ""
		table_str_list = table_str.splitlines(True)

		default_action_name = ""
		actions_start = False

		for line in table_str_list:
			if len(line.strip()) == 0: # skip empty line
				continue
			def_table = lang_helper.lib_parser_ingress_table_start(line)
			if def_table:
				table_name = def_table.group(1).strip()
				if table_name in self.table_set:
					res_str += line.replace(table_name, "%s_%s" %(self.table_prefix, table_name))

			actions = lang_helper.lib_parser_ingress_table_actions_start(line, lang_version)
			if actions:
				actions_start = True
			if actions_start:
				for action_name in self.action_set:
					if action_name in line:
						line = line.replace(action_name, "%s_%s" %(self.output_prefix, action_name))
				res_str += line
				if '}' in line:
					actions_start = False
					continue

			default_action = lang_helper.lib_parser_ingress_table_default_action_start(line, lang_version)
			if default_action:
				default_action_name = default_action.group(2).strip()
				for action_name in self.action_set:
					if action_name in line:
						line = line.replace(action_name, "%s_%s" %(self.output_prefix, action_name))
				res_str += line

			if (not def_table) and (not actions_start) and (not default_action):
				res_str += line
		return res_str

	def generate_p4_apply_rule_code(self):
		"""
		Description: the function generates the P4-16 code for apply logic.
		It has to add the prefix to actions and tables respectively.
		"""
		self.p4_apply_code = ""
		for apply_key in self.apply_rule.keys():
			if apply_key == 'ingress':
				apply_line_list = self.apply_rule['ingress'].splitlines(True)
				#print apply_line_list
				for line_count, line in enumerate(apply_line_list):
					if line_count == 0 or line_count == len(apply_line_list)-1:
						continue
					for action_name in self.action_set.keys():
						#if action_name == "set_dmac":
						#	print line, '\t' in line
						if ((' '+action_name) in line) or (('\t'+action_name) in line):
							line = line.replace(action_name, self.output_prefix+"_"+action_name)
					for table_name in self.table_set.keys():
						if (table_name+".apply()") in line:
							line = line.replace(table_name, self.table_prefix+"_"+table_name)

					self.p4_apply_code += line
		return

	def generate_p414_apply_rule_code(self):
		"""
		Description: the function generates the P4-14 code for apply logic.
		It has to add the prefix to tables respectively.
		Note: in p4-14, actions cannot be called in the control block
		"""
		self.p4_apply_code = ""
		for apply_key in self.apply_rule.keys():
			if apply_key == 'ingress':
				apply_lines = self.apply_rule['ingress'].splitlines(True)
				for line_cnt, line in enumerate(apply_lines):
					if line_cnt == 0 or line_cnt == len(apply_lines)-1:
						continue
					call_table = lang_helper.lib_parser_ingress_apply_call_table(line, 'p414')
					if call_table:
						table_name = call_table.group(1).strip()
						line = line.replace(table_name, self.table_prefix+"_"+table_name)
					self.p4_apply_code += line
		return

	def generate_p4_default_code(self):
		"""
		This function will generate the default code for a myIngress function
		by updating the self.p4_code.
		You can also use this function to generate the default P4 code by initializing
		the class ingress_match_action object with a str (input_p4_code)
		"""
		if self.p4_code == None:
			self.p4_code = ""

		ingress_head_code = ""
		ingress_head_code += "/*************************************************************************\n"
		ingress_head_code += "**************  I N G R E S S   P R O C E S S I N G   *******************\n"
		ingress_head_code += "*************************************************************************/\n\n"
		ingress_head_code += "control MyIngress(inout headers hdr,\n"
		ingress_head_code += "\tinout metadata meta,\n"
		ingress_head_code += "\tinout standard_metadata_t standard_metadata) {\n"

		self.p4_code = ingress_head_code + self.p4_code
		self.p4_code += "} // END myIngress\n"

		return

	def generate_p4_spi_selector_table(self):
		"""
		This function will generate the code for the P4 service path selector table.
		For apply{...}, there is only one line of code, i.e.
		network_service_path_selector_table.apply();

		For the table definition part, we will have one action for each service path
		in the whole NF graph.
		Input: # of network service paths (Int)
		Output: P4 code ?
		"""
		return

def my_ingress_tester():
	print "NF Chain Parser begins:"
	
	print "List all P4-lib scripts:"
	subprocess.call(['ls', '../p4_lib'])
	'''
	"""
	Test p4_table
	"""
	selector_table = p4_table("", "conn_table", 50)
	print selector_table.generate_p4_code()
	#return
	'''

	input_filename = '../p4_lib/'+raw_input("Please input filename:\n")
	ingress = ingress_match_action()
	ingress.read_default_prefix(input_filename)
	print ingress.output_prefix
	print "*******************\n"

	ingress.read_actions(input_filename)
	ingress.generate_p4_action_code()
	"""
	print "Action num:", len(ingress.action_set)
	for action_key, action_value in ingress.action_set.items():
		print action_key
		print action_value
	"""
	print "Test: print ingress action code\n", ingress.p4_action_code
	print "*******************\n"
	

	ingress.read_tables(input_filename)
	ingress.generate_p4_table_code()
	"""
	print "Table num:", len(ingress.table_set)
	for table_key, table_value in ingress.table_set.items():
		print table_key
		print table_value
	"""
	print "Test: print ingress table code\n", ingress.p4_table_code
	print "*******************\n"


	ingress.read_apply_rule(input_filename)
	ingress.generate_p4_apply_rule_code()
	print "Test: print ingress apply code\n", ingress.p4_apply_code
	print "*******************\n"



	ingress.generate_p4_code()
	print "Test: print p4 code\n", ingress.p4_code
	return

if __name__ == '__main__':

	my_ingress_tester()

