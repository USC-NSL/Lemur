"""
NFCP_BESS_GENERATOR.PY
This script converts NF chain graph into BESS code pipelines

Author: Jane Yen
Time: 07/18/2018
Email: yeny@usc.edu
"""

import re
import logging
from user_level_parser.UDLemurUserListener \
    import convert_nf_graph
from nf_placement import log_module, segment_module_list

#create logger
BESS_LOGGER = logging.getLogger("BESS_logger")
BESS_LOGGER.setLevel(logging.DEBUG)

FH = logging.FileHandler('bess.log')
FH.setLevel(logging.DEBUG)
FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
FH.setFormatter(FORMATTER)

BESS_LOGGER.addHandler(FH)

# global variables
'''
This list is used to store the NF instance and arguments \
that are already written in script
'''
FUNC_AND_ARGU_LIST = []

# constant string literals
SERVER_PCI = '5e:00.0'
PRECOMPUTE_LINE = ("nsh::NSHdecap()\nmyport=PMDPort(pci=\'%s\')" % SERVER_PCI)
PORTIN_LINE = "pin::PortInc(port=myport) -> nsh"
PORTOUT_LINE = "queue::Queue()->pout::PortOut(port=myport)"
CONDITION_LIST = { \
    'dst_ip': 'dst host', 'src_ip': 'src host', \
    'sport_tcp': 'tcp src port', 'dport_tcp': 'tcp dst port', \
    'gate_select': 'gate select'
}
CORE_LINE = ("for i in range(16):\n\tbess.add_worker(i,i)\n")
CORE_RESERVE_LINE = ("for i in range(2):\n\tpin.attach_task(wid=i)\nqueue.attach_task(wid=3)\n")

TC_CLASS = "TrafficShaper"
def define_tc(tc_queue_name):
    TC_LINE = "bess.add_tc('%s', policy='rate_limit', resource='bit', max_burst={'bit': 100000000000}, limit={'bit': 100000000000})" %(tc_queue_name)
    return TC_LINE

# func definition
def print_node_adjacent(linked_list):
    '''
    This function is a debug func that would print out \
    how many adjacent nodes and their names. The input \
    would be a linked list containing node information. \
    There is no return value for this func.
    '''
    BESS_LOGGER.info('called print_node_adjacent')
    nf_graph = convert_nf_graph(linked_list)
    modules = nf_graph.list_modules()
    for node in modules:
        BESS_LOGGER.debug("NF: %s, # adjacent %d nodes:", node.nf_class, len(node.adj_nodes))
        for adj_node in node.adj_nodes:
            BESS_LOGGER.debug("adjacent module class: %s", adj_node.nf_class)
    return

def script_initial():
    '''
    This func is called when BESS script file is opened. \
    It sets up shared NSHencap node for all BESS pipelines. \
    No input is fed to the func, and it returns the setup \
    codes in a list data structure.
    '''
    BESS_LOGGER.info('called script_initial')
    script_nshsetup = []
    script_nshsetup.append(PRECOMPUTE_LINE)
    script_nshsetup.append(PORTIN_LINE)
    script_nshsetup.append(PORTOUT_LINE)
    script_nshsetup.append(CORE_LINE)
    script_nshsetup.append(CORE_RESERVE_LINE)
    return script_nshsetup

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

def set_bounce_and_merge(modules_list, nfcp_parser, output_code_list):
    '''
    This func is used to check whether next module is going to receive \
    bounce packets and mark 'merge' bit if the the next module is a \
    merge node. It takes three inputs: module liat, a parser data structure \
    and a list of codes that would be written in BESS runnable script.
    The output would be the list of codes that'll be written in BESS \
    runnable script.
    '''
    BESS_LOGGER.info('called set_bounce_and_merge')
    global FUNC_AND_ARGU_LIST
    for module in modules_list:
        for adj_node in module.adj_nodes:
            output_code_list = register_check(adj_node, nfcp_parser, output_code_list)
            if not adj_node.bounce:
                adj_node.bounce = (adj_node.nf_type != module.nf_type)
            if (adj_node.service_path_id != module.service_path_id) and \
               (len(module.adj_nodes) == 1):
                adj_node.merge = True
    BESS_LOGGER.info('ended set_bounce_and_merge')
    return output_code_list, modules_list

def filter_func(condition):
    '''
    This func is used to parse branching condition and change condition \
    into valid BPF syntax. The input would be the branching condition \
    string and the output would be valid BPF sytax string. The input \
    condition can be something like [{'dst_ip': '10.0.0.2'}], and the \
    output would be changed to bpf syntax like "dst host 10.0.0.2"
    '''
    BESS_LOGGER.info('called filter_func')
    elem = re.findall("'.*?'", str(condition))
    elem = [i.replace("'", "") for i in elem]
#    print "elem", elem
    if len(elem)>1:
        para = elem[1]
        condition_type = CONDITION_LIST.get(elem[0])
    else:
        para = ""
        condition_type = ""
    return "%s %s" %(condition_type, para)


def new_branch_add(module, pipeline_code):
#def new_branch_add(module, branch_index, pipeline_code):
    '''
    This func could be repeatedly called whenever there is a branching \
    from the input module, and it will set up BPF nodes to split traffic. \
    The input would be current pipeline code ready to be written in script, \
    the module to branch and the increment branch_id. The output would be \
    BPF node declaration, pipeline_code added with bpf module and rule \
    registered for branching condition.
    '''
    #BESS_LOGGER.debug('%s called new_branch_add', instance_or_name(module))
    #branch_init = ("bpf%d::BPF()\n" % branch_index)
    #pipeline_code += ("-> bpf%d" % branch_index)
    #pipeline_code += ("-> %s" % module.name)
    branch_add = ''
    gate_count = 0
    for adj_node in module.adj_nodes:
        adj_node.bpf_gate = gate_count
        adj_node.nf_node_set_branch_str("%s:%d" % (module.name, gate_count))
        #print adj_node.nf_class, adj_node.transition_condition 
        filter_parse = filter_func(adj_node.transition_condition)
        line = ('%s.add(filters=[{\"filter\": \"%s\", \"gate\": %d}])\n' % \
            (module.name, filter_parse, gate_count))
        branch_add += line
        gate_count += 1
    return  pipeline_code, branch_add, module

def instance_or_name(module, nfcp_parser):
    '''
    This func check whether a module is anonymous or with argument. \
    The input is module itself, and the output would be either module \
    instance or module class declaration with/without argument.
    '''
    module_arg = ''
    return_str = ''
    combine_ls = dict(nfcp_parser.scanner.var_string_dict.items() + \
        nfcp_parser.scanner.var_int_dict.items() + \
        nfcp_parser.scanner.var_float_dict.items() + \
        nfcp_parser.scanner.var_bool_dict.items()
    )
    if module.argument != None:
        '''    
        line = ("%s = \"%s\"" % \
            (module.argument, nfcp_parser.scanner.var_string_dict[module.argument]))
        module_arg = line
        print "line", line
        '''
        if module.argument in combine_ls:
#            print combine_ls[module.argument]
            module_arg = combine_ls[module.argument]
    if module.name.split()[0] != 'anon':
        return_str = module.name
    else:
        if module.nf_class==TC_CLASS:
            tc_q_name = 'tc_%d_%d_q' %(module.service_path_id, module.service_id)
            return_str = tc_q_name
        else:
            return_str = "%s(%s)" % (module.nf_class, module_arg)
    return return_str

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

def name_register(module, func_and_argu_list_copy):
    '''
    This func checks if the func or argument instance has been declared/written \
    to BESS runnable script code. The input is the module and the global list \
    of all registered func and arguments. If the instance name is not yet, \
    it would return True value indicating there requires instance register.
    '''
    #BESS_LOGGER.debug('%s called name_register', (instance_or_name(module)))
    return_bool = True
    if module.name.split()[0] != 'anon':
        return_bool = module.name in func_and_argu_list_copy
    else:
        return_bool = True
    return return_bool

def register_check(module, nfcp_parser, output_code_list):
    '''
    This func check if the module will be called with instance name and \
    register the declaration of instance to output_code_list. This func \
    takes module, nfcp_parser and output_code_list as input, and returns \
    processed output_code_list.
    '''
    #BESS_LOGGER.debug('%s called register check', (instance_or_name(module)))
    global FUNC_AND_ARGU_LIST
    '''
    if module.argument != None:
        if module.argument in FUNC_AND_ARGU_LIST:
            pass
        else:
            FUNC_AND_ARGU_LIST.append(module.argument)
            output_code_list.append(line)
    '''
    if not name_register(module, FUNC_AND_ARGU_LIST):
        line = ("%s = %s" % (module.name, class_and_arg(module)))
        FUNC_AND_ARGU_LIST.append(module.name)
        output_code_list.append(line)
    return output_code_list

def setup_pipeline(modules_list, nfcp_parser, nsh_gate_count_value, branch_id_value, queue_count):
    '''
    This func is the main pipeline setup code. It will take a list of module \
    belonging to the same nf chain and nfcp_parser as input. The output will \
    be a list of code lines that's used to generate bess runnable script.
    '''
    global FUNC_AND_ARGU_LIST
    pipeline_code = ''
    output_code_list = []
    output_code_list = set_bounce_and_merge(modules_list, nfcp_parser, output_code_list)
    modules_list[0].reset_mark()
    for module in modules_list:
        output_code_list = register_check(module, nfcp_parser, output_code_list)
        if module.is_bess():                 # only treat BESS modules
            BESS_LOGGER.debug('module %s nf_type: %d', module.nf_class, module.nf_type)
            if (module.bounce or module.reset):
                if module.merge:
                    tmp_str = ("%s" % \
                        (instance_or_name(module, nfcp_parser)))
                else:
                    queue_padding = ''
                    if module.optimize:
                        queue_padding = ("q%d::Queue()->" % queue_count)
                        output_code_list.append("bess.add_worker(%d,%d)" % (queue_count, queue_count))
                        queue_count+=1
                    tmp_str = ("nsh:%d -> %s" %(nsh_gate_count_value, queue_padding+instance_or_name(module, nfcp_parser)))
                    output_code_list.append(new_gate_add(module, nsh_gate_count_value))
                    nsh_gate_count_value += 1
                pipeline_code += tmp_str
            elif module.is_branched_out():
                branch_code = module.branch_str + ("-> %s" % instance_or_name(module, nfcp_parser))
                pipeline_code += branch_code
            else:
                if module.branch_str.strip() != '':
                    pipeline_code += module.branch_str
                pipeline_code += ("-> %s" % instance_or_name(module, nfcp_parser))

            if module.is_branch_node():
                branch_init, pipeline_code, branch_add = \
                    new_branch_add(module, branch_id_value, pipeline_code)
                branch_id_value += 1
                output_code_list.append(branch_init)
                output_code_list.append(pipeline_code)
                output_code_list.append(branch_add)
                pipeline_code = ''
            else:
                adj_node = module.adj_nodes[0]
                #adj_node.setup_node_nf_type()
                if adj_node.is_p4():
                    adj_node.bounce = True
                    pipeline_code += ("-> NSHencap(new_spi=\'%d\', new_si=\'%d\')-> queue" % \
                        (adj_node.service_path_id, adj_node.service_id))
                    output_code_list.append(pipeline_code)
                    pipeline_code = ''
                elif adj_node.merge:
                    pipeline_code += ("-> %s" % instance_or_name(adj_node, nfcp_parser))
                    output_code_list.append(pipeline_code)
                    pipeline_code = ''
        else:
            if module.is_branched_out():
                pipeline_code += module.branch_str
                pipeline_code += ("-> NSHencap(new_spi=\'%d\', new_si=\'%d\')-> queue" % \
                    (module.service_path_id, module.service_id))
                output_code_list.append(pipeline_code)
                pipeline_code = ''
            if module.not_end_of_chain() and (module.adj_nodes[0].merge) and (module.adj_nodes[0].is_bess()):
                pipeline_code = ("nsh:%d -> %s" % (nsh_gate_count_value, \
                    instance_or_name(module.adj_nodes[0], nfcp_parser)))
                output_code_list.append(new_gate_add(module.adj_nodes[0], nsh_gate_count_value))
                nsh_gate_count_value += 1
                output_code_list.append(pipeline_code)
                pipeline_code = ''
    return output_code_list, nsh_gate_count_value, branch_id_value, queue_count

def sort_list(module_list):
    '''
    Sort modules of a chain in the order of chain order. Otherwise, the pipeline \
    setup might cause issues. The input is a list of modules within an nf chain, \
    and the output is the sorted module list.
    '''
    BESS_LOGGER.info('calling sort_list func')
    module_list.sort(key=lambda l: (not l.reset, l.service_path_id, l.service_id))
    return module_list

'''
def segment_module_list(all_modules):
#    all_modules = sort_list(all_modules)
    cut_index = []
    start = 0
    chain_module_list = []
    for module in all_modules:
        if len(module.adj_nodes)==0:
            cut_index.append(all_modules.index(module))
    for index in cut_index:
        module_list = all_modules[start: index+1]
        start = index+1
        chain_module_list.append(module_list)
    return chain_module_list
'''
def new_setup_pipeline(module_list, nfcp_parser, nsh_gate_count_value, branch_index, queue_index, rr_index, core_index):
    '''
    Setup nsh gates
    '''
    output_code_list = []
    tc_code_list = []
    output_code_list, module_list = set_bounce_and_merge(module_list, nfcp_parser, output_code_list)
    if module_list[0].is_bess():
        module_list[0].bounce = True

    find_first = False
    for module in module_list:
        if (not find_first) and module.is_bess():
            module.reset = True
            find_first = True
            break
    log_module(module_list)
    for module in module_list:
        if module.is_bess() and module.bounce:
            output_code_list.append(new_gate_add(module, nsh_gate_count_value))
            module.nsh_gate = nsh_gate_count_value
            nsh_gate_count_value +=1
        if module.nf_class == TC_CLASS:
            tc_q_name = 'tc_%d_%d_q' %(module.service_path_id, module.service_id)
            tc_queue = '%s::Queue()\n' %(tc_q_name)
            output_code_list.append(tc_queue)

    memory_array_1 = []
    memory_array_2 = []
    global_branch_core_num = 0
    last_core_num = 1
    for module in module_list:
        if module.is_p4():
            if module.is_branched_out():
                for item_1 in memory_array_1:
#                    print memory_array_1
                    push_out_str = item_1+(':%d->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (module.bpf_gate, module.service_path_id, module.service_id))
                    output_code_list.append(push_out_str)
                    if item_1 in memory_array_2:
                        memory_array_2.remove(item_1)
            elif module.bounce:
                '''
                if module.is_branched_out():
                   
                    for item_1 in memory_array_1:
                        push_out_str = item_1+('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (module.service_path_id, module.service_id))
                        output_code_list.append(push_out_str)
                '''   
                if len(memory_array_2) >0 :
                    memory_array_3 = memory_array_2[-global_branch_core_num:]
                    memory_array_2 = memory_array_2[:-global_branch_core_num]
                    for item_2 in memory_array_3:
                        push_out_str = item_2+('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (module.service_path_id, module.service_id))
                        output_code_list.append(push_out_str)
                elif len(memory_array_1) > 0:
                    for item_1 in memory_array_1:
                        push_out_str = item_1+('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (module.service_path_id, module.service_id))
                        output_code_list.append(push_out_str)
            global_branch_core_num = 0
            for adj_node in module.adj_nodes:
                if adj_node.is_bess():
#                    print 'enter here'
                    if module.is_branched_out() or len(memory_array_2)>0:
                        memory_array_2.append('nsh:%d' % adj_node.nsh_gate)
                    elif len(memory_array_1) >0:
                        memory_array_1.append('nsh:%d' % adj_node.nsh_gate)
                    global_branch_core_num += 1

        elif module.is_bess():
            
            if module.nf_class == TC_CLASS: # add BESS tc
                tc_q_name = 'tc_%d_%d_q' %(module.service_path_id, module.service_id)
                tc_code_list.append(define_tc(tc_q_name))
                
            if module.reset:
            #if module.reset or module.bounce:
                if module.core_num == last_core_num:
                    if module.reset:
                        push1_str = ('nsh:%d -> q%d::Queue() -> %s' % (module.nsh_gate, queue_index, instance_or_name(module, nfcp_parser)))
                        memory_array_1.append(push1_str)
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        queue_index += 1
                        if module.is_branch_node():
                            item_index = 0
                            for item in memory_array_1:
                                branch_init, item, branch_add, module = new_branch_add(module, branch_index, item)
                                output_code_list.append(branch_init)
                                output_code_list.append(item)
                                output_code_list.append(branch_add)
                                memory_array_1[item_index] = ('bpf%d' % branch_index)
                                memory_array_2.append('bpf%d' % branch_index)
                                branch_index += 1
                                item_index += 1

                    '''
                    else:
                        push1_str = ('nsh:%d -> %s' % (module.nsh_gate, instance_or_name(module, nfcp_parser)))
                        memory_array_1.append(push1_str)
                    '''
                else:
                    push1_str = ('nsh:%d -> q%d::Queue() -> rr%d::RoundRobin(gates=range(%d))' % (module.nsh_gate, queue_index, rr_index, module.core_num))
                    output_code_list.append(push1_str)
                    tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                    queue_index += 1
                    core_index += 1
                    for i in range(module.core_num-1):
                        push1_str = ('rr%d:%d -> q%d::Queue() -> %s' % (rr_index, i, queue_index, instance_or_name(module, nfcp_parser)))
                        memory_array_1.append(push1_str)
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        queue_index += 1
                    rr_index += 1
                    if module.is_branch_node():
                        item_index = 0
                        for item in memory_array_1:
                            branch_init, item, branch_add, module = new_branch_add(module, branch_index, item)
                            output_code_list.append(branch_init)
                            output_code_list.append(item)
                            output_code_list.append(branch_add)
                            memory_array_1[item_index] = ('bpf%d' % branch_index)
                            #item = ('bpf%d' % branch_index)
                            branch_index += 1
                            item_index += 1
                            #print("here: %s" % memory_array_1)
                
                if module.nf_class == TC_CLASS: # add BESS tc
                    tc_q_name = 'tc_%d_%d_q' %(module.service_path_id, module.service_id)
                    tc_code_list.append("%s.attach_task(parent='%s')" % (tc_q_name, tc_q_name))

            elif module.is_branch_node():
            #elif len(module.adj_nodes)>1:
                #print "branch_node"
                if module.core_num == last_core_num:
                    for item in memory_array_1:
                        item += ('-> %s' % instance_or_name(module, nfcp_parser))
                        branch_init, item, branch_add = new_branch_add(module, branch_index, item)
                        if not (branch_init in output_code_list):
                            output_code_list.append(branch_init)
                            output_code_list.append(branch_add)
                        output_code_list.append(item)
                        item = ('bpf%d' % branch_index)
                    branch_index += 1
                else:
                    output_code_list.append('q%d::Queue()' % queue_index)
                    for item in memory_array_1:
                        item += ('->q%d' % (queue_index))
                        output_code_list.append(item)
                        output_code_list.append('q%d -> rr%d::RoundRobin(gates=range(%d))' % (queue_index, rr_index, module.core_num))
                    queue_index += 1
                    memory_array_1 = []
                    for i in range(module.core_num):
                        memory_array_1.append('rr%d:%d -> q%d::Queue() -> %s' % (rr_index, i, queue_index, instance_or_name(module, nfcp_parser)))
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        queue_index += 1
                    item_index = 0
                    for item in memory_array_1:
                        branch_init, item, branch_add, module = new_branch_add(module, branch_index, item)
                        output_code_list.append(branch_init)
                        output_code_list.append(item)
                        output_code_list.append(branch_add)
                        memory_array_1[item_index] = ('bpf%d' % branch_index)
                        branch_index += 1
                    rr_index += 1
            elif module.is_branched_out():
                global_branch_core_num = 0
                if module.core_num == last_core_num:
                    for item in memory_array_1:
                        memory_array_2.append(item + (':%d -> %s' % (module.bpf_gate, instance_or_name(module, nfcp_parser))))
                        global_branch_core_num += 1
                else:
                    output_code_list.append('q%d::Queue()' % queue_index)
                    for item in memory_array_1:
                        item2 = item + ('-> q%d' % (queue_index))
                        output_code_list.append(item2)
                        output_code_list.append('q%d -> rr%d::RoundRobin(gates=range(%d))' % (queue_index, rr_index, module.core_num))
                    queue_index += 1
                    for i in range(module.core_num):
                        memory_array_2.append('rr%d:%d -> q%d::Queue() -> %s' % (rr_index, i, queue_index, instance_or_name(module, nfcp_parser)))
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        global_branch_core_num += 1
                        queue_index += 1
                    rr_index += 1
            elif module.merge:
                if module.core_num == last_core_num:
                    output_code_list.append('q%d::Queue()' % queue_index)
                    memory_array_1 = []
                    for item in memory_array_2:
                        item += ('->q%d' % queue_index)
                        #item += ('->%s' % instance_or_name(module, nfcp_parser))
                        output_code_list.append(item)
                    memory_array_2 = []
                    memory_array_1.append('q%d->%s' % (queue_index, instance_or_name(module, nfcp_parser)))
                    queue_index += 1
                else:
                    output_code_list.append('q%d::Queue()' % queue_index)
                    for item in memory_array_2:
                        item+=('->q%d' % queue_index)
                        output_code_list.append(item)
                    memory_array_2 = []
                    memory_array_1 = []
                    output_code_list.append('q%d->rr%d::RoundRobin(gates=range(%d))' % (queue_index, rr_index, module.core_num))
                    queue_index += 1
                    for i in range(module.core_num):
                        memory_array_1.append('rr%d:%d -> q%d::Queue() -> %s' % (rr_index, i, queue_index, instance_or_name(module, nfcp_parser)))
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        queue_index += 1
                    rr_index += 1
            elif len(memory_array_2) > 0:
                if module.core_num == last_core_num:
                    memory_array_3 = memory_array_2[-global_branch_core_num:]
                    item_index = 0
                    for item in memory_array_3:
                        memory_array_2[-global_branch_core_num+item_index] = item + ('-> %s' % instance_or_name(module, nfcp_parser))
                        item_index += 1
                else:
                    ouput_code_list.append('q%d::Queue()' % queue_index)
                    memory_array_3 = memory_array_2[-global_branch_core_num:]
                    memory_array_2 = memory_array_2[:-global_branch_core_num]
                    for item in memory_array_3:
                        item += ('-> q%d' % queue_index)
                        output_code_list.append(item)
                    output_code_list.append('q%d->rr%d::RoundRobin(gates=range(%d))' % (queue_index, rr_index, module.core_num))
                    queue_index += 1
                    for i in range(module.core_num):
                        memory_array_2.append('rr%d:%d -> q%d::Queue() -> %s' % (rr_index, i, queue_index, instance_or_name(module, nfcp_parser)))
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        queue_index += 1
                    rr_index += 1
            else:

                if module.nf_class == TC_CLASS:
                    # add tc_code
                    tc_q_name = 'tc_%d_%d_q' %(module.service_path_id, module.service_id)
                    tc_code_list.append("%s.attach_task(parent='%s')" %(tc_q_name, tc_q_name))

                #print module, module.core_num, memory_array_1, instance_or_name(module, nfcp_parser)
                if module.core_num == last_core_num:
                    if len(memory_array_2) >0:
                        for item in memory_array_2:
                            item += ('->%s' % instance_or_name(module, nfcp_parser))
                    elif len(memory_array_1) >0:
                        for item in memory_array_1:
                            item += ('->%s' % instance_or_name(module, nfcp_parser))
                else:
                    output_code_list.append('q%d::Queue()' % queue_index)
                    for i, item in enumerate(memory_array_1):
                        item += ('-> q%d' % queue_index)
                        output_code_list.append(item)
                    output_code_list.append('q%d->rr%d::RoundRobin(gates=range(%d))' % (queue_index, rr_index, module.core_num))
                    queue_index += 1
                    memory_array_1 = []
                    for i in range(module.core_num):
                        memory_array_1.append('rr%d:%d -> q%d::Queue() -> %s' % (rr_index, i, queue_index, instance_or_name(module, nfcp_parser)))
                        tc_code_list.append('q%d.attach_task(wid=%d)' % (queue_index, core_index))
                        core_index += 1
                        queue_index += 1
                    rr_index += 1
            last_core_num = module.core_num
            for adj_node in module.adj_nodes:
                if adj_node.is_p4():
                    if adj_node.is_branched_out():
                        for item_1 in memory_array_1:
                            #print memory_array_1
                            push_out_str = item_1+(':%d->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (adj_node.bpf_gate, adj_node.service_path_id, adj_node.service_id))
                            output_code_list.append(push_out_str)
                            if item_1 in memory_array_2:
                                memory_array_2.remove(item_1)
                    elif adj_node.bounce:
                        '''
                        if module.is_branched_out():
                        for item_1 in memory_array_1:
                        push_out_str = item_1+('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (module.service_path_id, module.service_id))
                        output_code_list.append(push_out_str)
                        '''
                        if len(memory_array_2) >0 :
                            memory_array_3 = memory_array_2[-global_branch_core_num:]
                            memory_array_2 = memory_array_2[:-global_branch_core_num]
                            for item_2 in memory_array_3:
                                push_out_str = item_2+('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (adj_node.service_path_id, adj_node.service_id))
                                output_code_list.append(push_out_str)
                        elif len(memory_array_1) > 0:
                            for item_1 in memory_array_1:
                                push_out_str = item_1+('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->queue' % (adj_node.service_path_id, adj_node.service_id))
                                output_code_list.append(push_out_str)
                    global_branch_core_num = 0
                    '''
                    for adj_node in module.adj_nodes:
                    if adj_node.is_bess():
                        print 'enter here'
                        if module.is_branched_out() or len(memory_array_2)>0:
                            memory_array_2.append('nsh:%d' % adj_node.nsh_gate)
                        elif len(memory_array_1) >0:
                            memory_array_1.append('nsh:%d' % adj_node.nsh_gate)
                            global_branch_core_num += 1
                    '''

    return output_code_list, tc_code_list, nsh_gate_count_value, branch_index, queue_index, rr_index, core_index
               

def convert_graph_to_bess(nfcp_parser, all_modules):
    '''
    This func takes nfcp_parser data structure and convert it into runnable \
    bess script. The input is nfcp_parser, and the output is list of code lines.
    '''
    write_content = []
    write_content = script_initial()
    nsh_gatecount = 0
    queue_count = 0
    rr_count = 0
    branch_id = 0
    bess_core_index = 4
    BESS_LOGGER.info('bess_code_generation starts')
    BESS_LOGGER.info('calling scanner to retrive nfchains')

    all_module_list = segment_module_list(all_modules)
    for module_list in all_module_list:
        #log_module(module_list)
        str_list,tc_list, nsh_gatecount, branch_id, queue_count, rr_count, bess_core_index = \
            new_setup_pipeline(module_list, nfcp_parser, nsh_gatecount, branch_id, queue_count, rr_count, bess_core_index)
            
        if str_list != None:
            write_content += (str_list)
        if tc_list != None:
            write_content += (tc_list)
    BESS_LOGGER.info('bess_code_generation ends')
    return write_content
