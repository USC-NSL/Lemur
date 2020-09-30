"""
LEMUR_BESS_GENERATOR_UTIL.PY
This script converts NF chain graph into BESS code pipelines
"""

import re

def new_gate_add(module, gate_index, nic_name):
    '''
    This func is used to setup new gate at shared NSHdecap \
    module. The input would be a module, and the func would \
    add a gate at NSHdecap with SPI/SI = module's SPI/SI. \
    This func would return the code of whole setup.
    '''
    #BESS_LOGGER.debug("%s called new_gate_add", instance_or_name(module))
    line = ("%s_nsh.add(rule_spi=\'%d\', rule_si=\'%d\', gate=%d)" \
        % (nic_name, module.service_path_id, module.service_id, gate_index))
    return line

def new_branch_add(module, pipeline_code):
    '''
    This func could be repeatedly called whenever there is a branching \
    from the input module, and it will set up BPF nodes to split traffic. \
    The input would be current pipeline code ready to be written in script, \
    the module to branch and the increment branch_id. The output would be \
    BPF node declaration, pipeline_code added with bpf module and rule \
    registered for branching condition.
    '''
    branch_add = ''
    gate_count = 0
    for adj_node in module.adj_nodes:
        adj_node.bpf_gate = gate_count
        adj_node.nf_node_set_branch_str("%s:%d" % (module.name, gate_count))
        filter_parse = filter_func(adj_node.transition_condition)
        line = ('%s.add(filters=[{\"filter\": \"%s\", \"gate\": %d}])\n' % \
            (module.name, filter_parse, gate_count))
        branch_add += line
        gate_count += 1
    return  pipeline_code, branch_add, module

def class_and_arg(module, nfcp_parser):
    '''
    This func output a module with its class and argument. This is mostly \
    used to declare a module instance. The input is the module.
    '''
    module_arg = ''
    combine_ls = dict(nfcp_parser.scanner.var_string_dict.items() + \
        nfcp_parser.scanner.var_int_dict.items() + \
        nfcp_parser.scanner.var_float_dict.items() + \
        nfcp_parser.scanner.var_bool_dict.items()
    )
    if module.argument != None:
        if module.argument in combine_ls:
            module_arg = combine_ls[module.argument]
        else:
            module_arg = module.argument

    return "%s(%s)" % (module.nf_class, module_arg)

