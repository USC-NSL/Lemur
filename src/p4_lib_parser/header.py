
"""
* Title: header.py 
* Description:
* The script is used to parse the header definition part in the target file
*
* Author: Jianfeng Wang
* Time: 01/16/2018
* Email: jianfenw@usc.edu
*
"""
import sys
sys.path.append('..')
import copy
import header_lib
import collections
import re
import util.lang_parser_helper as lang_helper

class const_var_parser:
	def __init__(self, input_macro_list=None, input_const_list=None):
		self.macro_list = collections.OrderedDict()
		self.const_list = collections.OrderedDict()

		if input_macro_list != None:
			self.macro_list = copy.deepcopy(input_macro_list)
		if input_const_list != None:
			self.const_list = copy.deepcopy(input_const_list)

		self.p4_macro_code = None
		self.p4_const_code = None
		self.p4_code = None
		return

	def read_macros(self, filename):
		with open(filename, 'r') as fp:
			for line in fp:
				parse_macro = lang_helper.lib_parser_macro(line)
				if parse_macro:
					macro_key = parse_macro.group(1).strip()
					macro_val = parse_macro.group(2).strip()
					self.macro_list[macro_key] = macro_val
		return

	def generate_p4_macro_code(self):
		if self.p4_macro_code == None:
			self.p4_macro_code = ""
		res = ""
		for macro_key, macro_val in self.macro_list.items():
			res += "#define %s %s\n" %(macro_key, macro_val)
		self.p4_macro_code = res
		return

	def read_const_variables(self, filename):
		# Sample const: 
		# const bit<16> TYPE_IPv4 = 0x0800;
		with open(filename, 'r') as fp:
			for line in fp:
				line = line.strip()
				curr_res = re.match(r'add_const\((.*),(.*),(.*)\)', line, re.M|re.I)
				if curr_res != None:
					curr_const = curr_res.span()
					# group 1 - name; group 2 - type; group 3 - value
					# In the dictionary, self.const_list[const_name] = (type, value)
					curr_const_name = curr_res.group(1)
					curr_const_def = ( curr_res.group(2), curr_res.group(3) )
					self.const_list[curr_const_name] = curr_const_def
		return

	def generate_p4_const_code(self):
		if self.p4_const_code == None:
			self.p4_const_code = ""

		res = ""
		for key, val in self.const_list.items():
			# const bit<16> TYPE_IPV4 = 0x0800
			res += "const %s %s = %s;\n" %(val[0], key, val[1])
		res += "\n"

		self.p4_const_code = res
		return

	def generate_p4_code(self):
		res_code = ""
		self.generate_p4_macro_code()
		res_code += self.p4_macro_code

		self.generate_p4_const_code()
		res_code += self.p4_const_code
		self.p4_code = res_code
		return

	def generate_p414_code(self):
		res_code = ""
		self.generate_p4_macro_code()
		res_code += self.p4_macro_code

		self.generate_p4_const_code()
		res_code += self.p4_const_code
		self.p4_code = res_code
		return

class header_parser:

	def __init__(self, input_header_list=[], input_metadata_list=collections.OrderedDict()):
		self.headers = copy.deepcopy(input_header_list)
		self.metadata = copy.deepcopy(input_metadata_list)
		self.p4_header_code = None
		self.p4_meta_code = None
		self.p4_code = None
		return

	def read_headers(self, filename):
		headers = []
		with open(filename, 'r') as fp:
			for line in fp:
				line = line.strip()
				if line == '':
					continue
				if line[:7] == "#define":
					headers.append(line[8:])

		self.headers += (headers)
		return

	def generate_p4_header_code(self):
		if self.p4_header_code == None:
			self.p4_header_code = ""

		res = ""
		for hd in self.headers:
			if hd.lower() in header_lib.all_header_list:
				res += "header " + hd.lower()+"_t {" +"\n"
				for field in header_lib.all_header_list[hd.lower()]:
					res +=  field.generate_p4_code()
				res += "}\n\n"

		self.p4_header_code = res
		return

	def generate_p414_header_code(self):
		if self.p4_header_code == None:
			self.p4_header_code = ""
		res = ""
		for hd in self.headers:
			if hd.lower() in header_lib.all_header_list:
				res += "header_type %s_t {\n" %(hd.lower())
				res += "\tfields{\n"
				for field in header_lib.all_header_list[hd.lower()]:
					res += field.generate_p414_code()
				res += "\t}\n}\n\n"

		self.p4_header_code = res
		return

	def read_metadata(self, filename):
		metadata = []
		with open(filename, 'r') as fp:
			line_count = 0
			for line in fp:
				line_count += 1
				line = line.strip()
				if line == '':
					continue

				if 'add' in line and 'metadata(' in line:
					meta_seq_start = line.index('(')
					meta_seq_end = line.index(')')
					meta_seq_string = line[ meta_seq_start+1 : meta_seq_end ].strip()
					if meta_seq_string == "":
						continue

					meta_field = meta_seq_string.split(',', 2)
					self.metadata[meta_field[0].strip()] = meta_field[1].strip()
		return

	def generate_p4_metadata_code(self):
		if self.p4_meta_code == None:
			self.p4_meta_code = ""
		
		res = ""
		res += "struct metadata {\n"
		for meta_field in self.metadata:
			res += "\t%s %s;\n" %(self.metadata[meta_field] , meta_field)
		res += "}\n\n"

		self.p4_meta_code = res
		return

	def generate_p414_metadata_code(self):
		if self.p4_meta_code == None:
			self.p4_meta_code = ""

		res = "header_type metadata_t {\n"
		res += "\tfields {\n"
		for meta_field in self.metadata:
			res += "\t\t%s : %s;\n" %(meta_field, self.metadata[meta_field])
		res += "\t}\n}\n\n"
		res += "metadata metadata_t meta;\n\n"
		self.p4_meta_code = res
		return

	
	def generate_p4_default_code(self):
		""" Description: the function is used to generate the default code for the header definition part.
		Note: it should also declare some commonly used 'macro's, such as macAddr_t.
		"""
		if self.p4_code == None:
			self.p4_code = ""

		header_head_code = ""
		header_head_code += "/*************************************************************************\n"
		header_head_code += "*********************** H E A D E R S  ***********************************\n"
		header_head_code += "*************************************************************************/\n\n"
		header_head_code += "typedef bit<9>  egressSpec_t;\n"
		header_head_code += "typedef bit<48> macAddr_t;\n"
		header_head_code += "typedef bit<32> ip4Addr_t;\n"
		header_head_code += "typedef bit<16> tcpPort_t;\n"
		header_head_code += "typedef bit<15> qdepth_t;\n"
		header_head_code += "typedef bit<32> digest_t;\n\n"

		header_tail_code = ""
		header_tail_code += "struct headers {\n"
		for hd in self.headers:
			if hd.lower() in header_lib.all_header_list:
				header_tail_code += "\t%s_t\t%s;\n" %(hd.lower(), hd.lower())
		header_tail_code += "}\n\n"

		self.p4_code = header_head_code + self.p4_code + header_tail_code
		return

	def generate_p414_default_code(self):
		if self.p4_code == None:
			self.p4_code = ""

		header_head_code = ""
		header_head_code += "/*************************************************************************\n"
		header_head_code += "*********************** H E A D E R S  ***********************************\n"
		header_head_code += "*************************************************************************/\n\n"

		header_tail_code = ""
		for hd in self.headers:
			if hd.lower() in header_lib.all_header_list:
				header_tail_code += "header %s_t %s;\n" %(hd.lower(), hd.lower())
		header_tail_code += "\n\n"

		self.p4_code = header_head_code + self.p4_code + header_tail_code
		return

	"""
		First, the library parser will call read_headers(...) and read_metadata(...)
		in order to parse the library file and store necessary information in the lists,
		i.e. self.headers and self.metadata.

		Then, the library parser will call generate_p4_code(...). This function will have
		to call self.generate_p4_header_code(...) and self.generate_p4_metadata_code(...)
		to generate the partial p4 code for the header part and the metadata part respectively.

		The generated code is stored in self.p4_code as a single string.
	"""
	def generate_p4_code(self):
		if self.p4_code == None:
			self.p4_code = ""

		res = ""
		self.generate_p4_header_code()
		res += "\n"
		res += self.p4_header_code

		self.generate_p4_metadata_code()
		res += "\n"
		res += self.p4_meta_code

		self.p4_code = res
		self.generate_p4_default_code()
		return

	def generate_p414_code(self):
		if self.p4_code == None:
			self.p4_code = ""

		res = ""
		self.generate_p414_header_code()
		res += "\n"
		res += self.p4_header_code

		self.generate_p414_metadata_code()
		res += "\n"
		res += self.p4_meta_code

		self.p4_code = res
		self.generate_p414_default_code()
		return

def header_parser_tester():
	print "Test 1 - cp macro parser and code generator"
	cp = const_var_parser()
	cp.read_macros("./p4_lib/acl.lib")
	cp.generate_p4_macro_code()
	print cp.p4_macro_code

	print "\nTest 2 - cp const variable parser and code generator"
	cp.read_const_variables("./p4_lib/acl.lib")
	cp.generate_p4_const_code()
	print cp.p4_const_code

	print "\nTest 3 - hp header parser ..."
	hp = header_parser()
	hp.read_headers("./p4_lib/acl.lib")
	#print hp.headers

	print "       - hp metadata parser ..."
	hp.read_metadata("./p4_lib/acl.lib")

	print "       - hp code generator ..."
	#hp.generate_p4_code()
	hp.generate_p414_code()
	print hp.p4_code


if __name__ == '__main__':

	header_parser_tester()

