"""
* This library includes helper functions for parsing user-level config
* files. Helper functions use regular expressions to scan, match, and
* parse key words in a piece of text.
*
"""

import re

# General Lang Parser Helper
def convert_str_to_list(gen_line):
	""" Convert a list (in str) to a real Python list.
	This function will convert a list written in string into a real python list
	e.g. "[a, b, c]" -> ['a', 'b', 'c']
	"""
	res = []
	parse_result_multi = re.match(r"\[(.*),(.*)\]", gen_line, re.M|re.I)
	if parse_result_multi:
		#print parse_result_multi.group(1), parse_result_multi.group(2)
		res += convert_str_to_list("[%s]"%(parse_result_multi.group(1)))
		res.append(parse_result_multi.group(2))
	else:
		parse_result_single = re.match(r"\[(.*)\]", gen_line, re.M|re.I)
		if parse_result_single:
			res.append(parse_result_single.group(1))
	return res


# User-level Lang Parser Helper
# Two lookup tables that converts key words used in an user-level config
# file to corresponding key words in the final P4 code.
global built_in_flowspec_lookup_table
global built_in_flowspec_lookup_table_p414
built_in_flowspec_lookup_table = { \
	'dst_ip':'hdr.ip.dstAddr', 'src_ip':'hdr.ip.srcAddr', \
	'sport_tcp':'hdr.tcp.srcPort', 'dport_tcp':'hdr.tcp.dstPort', \
	'prev_spi': 'meta.prev_spi', 'prev_si': 'meta.prev_si', \
	'gate_select': 'meta.gate_select'
	}
built_in_flowspec_lookup_table_p414 = { \
	'dst_ip':'ipv4.dstAddr', 'src_ip':'ipv4.srcAddr', \
	'sport_tcp':'tcp.srcPort', 'dport_tcp':'tcp.dstPort', \
	'prev_spi': 'meta.prev_spi', 'prev_si': 'meta.prev_si', \
	'gate_select': 'meta.gate_select'
	}


def match_stage_result(user_line):
	""" Parses switch stage usage.
	This function parses 'pipeline ingress requires at least (?) stages'
	"""
	parse_result = re.match(r"pipeline ingress requires at least (.*) stages", user_line, re.M|re.I)
	return parse_result


def is_empty_line(user_line):
	return (len(user_line.strip()) == 0)


def user_parser_traffic_type_old(user_line):
	"""
	Input: 'xxx_Traffic(arguments)'
	Ouput: res [= ('xxx_Traffic': arguments)] / otherwise return None
	"""
	res = None
	parse_result = re.match(r"(.*)\((.*)\)", user_line, re.M|re.I)
	# Match IP Traffic
	if parse_result and parse_result.group(1) == 'IP_Traffic':
		return ('IP_Traffic', convert_str_to_list(parse_result.group(2)) )
	# Match TCP Traffic
	if parse_result and parse_result.group(1) == 'TCP_Traffic':
		return ('TCP_Traffic', convert_str_to_list(parse_result.group(2)) )
	
	if parse_result and parse_result.group(1) == 'ALL_Traffic':
		return ('ALL_Traffic', [] )
	return res

def user_parser_traffic_type(user_line):
	"""
	Input: '{(a,b,c), (d,e,f)}'
	Ouput: ['(a,b,c)', '(d,e,f)']
	"""
	parse_result = re.match(r"\{(.*)\}", user_line, re.M|re.I)
	if parse_result == None:
		return None
	else:
		return parse_result.groups(1)

def user_parser_nickname(user_line):
	"""
	This function is used to parse 'instance_name = type_name'
	Input: str
	Output: key, value (e.g. instance_name, type_name)
	"""
	parse_result = re.match(r"\[\{(.*):(.*)\}\]", user_line, re.M|re.I)
	return parse_result.group(1).split(''), parse_result.group(2).split('')

def user_parser_nf_chain(user_line):
	"""
	This function parses "traffic: nf_chain".
	"""
	line = user_line.strip()
	parse_result = re.match(r"(.*):(.*)", line, re.M|re.I)
	return parse_result.group(1).strip(), parse_result.group(2).strip()


# Developer-level P4 library Parser Helper functions
# For P4 libraries, Lemur's compiler needs to parse different tags for
# each library, such as marco, header, parser, and apply.
def lib_parser_default_prefix(user_line):
	parse_result = re.match(r"default_prefix(.*)=(.*)", user_line, re.M|re.I)
	return parse_result

def lib_parser_macro(user_line):
	parse_result = re.match(r"add macro\((.*),(.*)\)", user_line, re.M|re.I)
	return parse_result

def lib_parser_header(user_line):
	return

def lib_parser_parser(user_line):
	return

def lib_parser_field_list_start(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^field_list (.*){", line, re.M|re.I)
	return parse_result

def lib_parser_field_list_calc_start(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^field_list_calculation (.*){", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_apply_start(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^apply(.*){", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_apply_call_table(user_line, lang_version):
	line = user_line.strip()
	if lang_version == 'p414': # apply(table_name);
		parse_result = re.match(r"^apply\((.*)\)([' ']*);", line, re.M|re.I)
	elif lang_version == 'p416': # table_name.apply();
		parse_result = re.match(r"^(.*).apply\(\)([' ']*);", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_table_start(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^table (.*){", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_table_match_start(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^reads {(.*)", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_table_match(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^(.*):(.*);", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_table_actions_start(user_line, lang_version):
	line = user_line.strip()
	if lang_version == 'p414': # actions { ;}
		parse_result = re.match(r"^actions {(.*)", line, re.M|re.I)
	elif lang_version == 'p416': # actions = { ;}
		parse_result = re.match(r"^actions = {(.*)", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_table_size(user_line):
	line = user_line.strip()
	parse_result = re.match(r"size(.*):(.*);", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_table_default_action_start(user_line, lang_version):
	line = user_line.strip()
	if lang_version == 'p414': # default_action : action_name;
		parse_result = re.match(r"^default_action(.*):(.*)(\(\))?;", line, re.M|re.I)
	elif lang_version == 'p416': # default_action = { ;}
		parse_result = re.match(r"^default_action(.*)=(.*);", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_action_start(user_line):
	line = user_line.strip()
	parse_result = re.match(r"^action (.*)\((.*)\)(.*){", line, re.M|re.I)
	return parse_result

def lib_parser_ingress_action_call_action(user_line, lang_version):
	line = user_line.strip()
	if lang_version == 'p414': # action_name();
		parse_result = re.match(r"^(.*)\((.*)\)(.*);", line, re.M|re.I)
	elif lang_version == 'p416': # action_name();
		parse_result = re.match(r"^(.*)\((.*)\)(.*);", line, re.M|re.I)
	return parse_result

def lib_parser_egress(user_line):
	return

def lib_parser_deparser(user_line):
	return

