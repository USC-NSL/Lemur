from __future__ import print_function
import os
import subprocess
import collections
import argparse
import itertools
import nfcp_user_level_parser as configParser
import nfcp_library_parser as libParser
import nfcp_code_generator as codeGenerator
import util.lang_parser_helper as lang_helper
import new_bess_generator as BG
from termcolor import colored
from util.lemur_nf_node import *
import util.lemur_nf_node as ND
from util.nfcp_install_table_entry import NFCP_entry_helper
from core.profile_p4 import p4_usage_checker
from connect import stage_feasible
from nfcp_compiler import get_argparse
from user_level_parser.UDLemurUserListener \
    import convert_nf_graph, convert_global_nf_graph
import nf_placement as placeTool
from nf_placement import log_module
import heuristic_util.graph as G

STATE_INIT = 0
global CONF_LIB
OUTPUT_DIR = "./"
global P414_LIB_DIR
CONF_LIB_DIR = "./user_level_examples"
P414_LIB_DIR = "./p4_14_lib/"
option_nf = []
global last_index
last_index = -1
global option_set
option_set = []


def parse_all_node(nfcp_parser):
    nf_graph = convert_global_nf_graph(nfcp_parser.scanner)
    modules = nf_graph.list_modules()
    modules.sort(key=lambda l: (l.service_path_id, l.service_id))
    return modules

def init_allp4(module_list):
    index = 0
    global last_index, option_set
    para_list,_ = placeTool.read_para()
    for module in module_list:
        if module.nf_type == 2:
            module.nf_type = 0
            option_nf.append([module.weight*int(para_list.get(str(module.nf_class))),index])
        index = index+1
    option_nf.sort(key = lambda l: l[0])
    option_set = list(option_nf)
    
    return module_list

def run_p4_compiler(p4_filename):
    status = stage_feasible(p4_filename)
    return status

def generate_code(conf_parser, module_list, p4_filename, p4_version):
    output_fp = open(p4_filename, 'w')
    output_fp.write("\n")
    p4_node_lists = conf_parser.conf_parser_get_global_p4_nodes(copy.deepcopy(module_list))
    default_nsh_node = nf_node()
    default_nsh_node.setup_node_from_argument('sys_default', 'SYS', 0, 0)
    p4_node_lists.insert(0, [default_nsh_node])
    all_p4_nodes = []
    for node_list in p4_node_lists:
        # for each service path, we do topo sorting
        node_list.sort(cmp=lambda x,y:cmp(x.finish_time, y.finish_time), reverse=True)
        all_p4_nodes += node_list
    p4_list = copy.deepcopy(all_p4_nodes)

    # Use 'nfcp_library_parser' to parse each P4 library
    # Method: libParser.nfcp_lib_parser(lib_repo, nf_node)
    print("NFCP Lib Parser is running...")

    for p4_node in p4_list:
        lib_filename = p4_14_module_list[p4_node.nf_class]
        if p4_version == 'p414':
            lib_dir = os.path.join(P414_LIB_DIR, lib_filename)
        elif p4_version == 'p416':
            lib_dir = os.path.join(P416_LIB_DIR, lib_filename)
        lib_parser = libParser.nfcp_lib_parser(lib_dir, p4_node)

    p4_generator = codeGenerator.nfcp_code_generator(conf_parser.scanner, p4_list, p4_version)
    print("NFCP P4 Library Combiner is running...")
    p4_generator.lib_combine_main()

    print("NFCP P4 Code Generator is running...")
    output_fp.write(p4_generator.code_generator_main())

    output_fp.close()
    print("NFCP Compiler Ends!")

def bess_code(conf_parser, all_nodes, final_bess_filename):
    bess_fp = open(final_bess_filename, 'w')
    BG.generate_bess(conf_parser, all_nodes)

def fitp4(conf_parser, module_list, p4_filename, p4_version):
    generate_code(conf_parser, module_list, p4_filename, p4_version)
    success_flag = run_p4_compiler(p4_filename)
    return success_flag

def next_placement_to_offload_p4(module_list):
    global last_index
    if len(option_nf) != 0:
        if(last_index!= -1):
            module_list[last_index].offload = False
            module_list[last_index].nf_type = 0
        pair = option_nf.pop(0)
        last_index = pair[1]
        module_list[last_index].offload = True
        module_list[last_index].nf_type = 1
    elif len(option_set)>0:
        fix_module = option_set.pop(0)
        fix_index = fix_module[1]
        module_list[fix_index].offload = True
        module_list[fix_index].nf_type = 1
        option_nf = list(option_set)
        module_list = next_placement_to_offload_p4(module_list)
    else:
        print("NO AVAILABLE PLACEMENT")

    return module_list

def highest_core_allocation_derived_from_LP(module_list):
    find_solution = False
    chosen_module_list = copy.deepcopy(module_list)
    throughput_list, bess_dict_para = placeTool.heuristic_core_allocation(module_list)
    
    if len(throughput_list)>0:
        find_solution = True
        chosen_pattern, core_alloc, expected_throughput = placeTool.optimize_pick(throughput_list)
        chosen_module_list = placeTool.apply_pattern(module_list, chosen_pattern, core_alloc, bess_dict_para)
    else:
        find_solution = False
        expected_throughput = 0
    return find_solution, chosen_module_list, expected_throughput

def least_change(throughput_dict):
    key = 0
    index = 0
    change_min = 10000000000000
    for dict_key in throughput_dict:
        for dict_value in throughput_dict[dict_key]:
            if dict_value<change_min:
                key = dict_key                
                index = throughput_dict[dict_key].index(dict_value)
                change_min = dict_value
    return key, index

def get_graph(chain_module):
    g = G.Graph(len(chain_module))
    for index in range(len(chain_module)):
        module = chain_module[index]
        for child in module.adj_nodes:
            g.addEdge(index, chain_module.index(child))
    return g

def can_offload(pair, chain, g):
    offload_route = []
    subgroup_1 = pair[0]
    subgroup_2 = pair[1]
    end_node_queue_1 = []
    end_node_queue_2 = []
    for node in subgroup_1:
        add_to_queue = False
        if len(node.adj_nodes)>0:
            for child in node.adj_nodes:
                if child not in subgroup_1:
                    add_to_queue = True
            if add_to_queue:
                end_node_queue_1.append(chain.index(node))
        else:
            print("SOMETHING IS WRONG HERE!")
            raise error

    for lead_node in subgroup_2:
#        print("node in group2: %s" % lead_node.nf_class)
        add_to_latter_queue = False
        if len(lead_node.prev_nodes)>0:
            for parent in lead_node.prev_nodes:
                if parent not in subgroup_2:
                    add_to_latter_queue = True
            if add_to_latter_queue:
                end_node_queue_2.append(chain.index(lead_node))
#    print("queue1 length %s, queue2 length %s" % (len(end_node_queue_1), len(end_node_queue_2)))
    src_dest = list(itertools.product(*([end_node_queue_1, end_node_queue_2])))
    for target_src_dest in src_dest:
        src = target_src_dest[0]
        dest = target_src_dest[1]
        route_list = g.printAllPaths(src,dest)
        for route in route_list:
            add_to_potential_bounce = True
            for route_index in route:
                if (chain[route_index].nf_class not in bess_module_list):
                    add_to_potential_bounce = False
            if add_to_potential_bounce:
                offload_route.append(route)
    return offload_route

def potential_better_placement(module_list, strict_flag):
    
    copy_module_list = copy.deepcopy(module_list)
    chain_module, _ = placeTool.segment_module_list(copy_module_list)
    offload_option = {}
    para_list, _ = placeTool.read_para()
    chain_rate = placeTool.get_rate()
    for chain in chain_module:
        g = get_graph(chain)
        chain_copy = copy.deepcopy(chain)
        chain_bess, chain_p4 = placeTool.bfs_sort(chain_copy)
        updated_chain_bess = copy.deepcopy(chain_bess)
        if len(updated_chain_bess)>1:
            for pair in itertools.combinations(updated_chain_bess, 2):
#                print("chain_index %s: pair %s" % (chain_module.index(chain), pair))
                offload_route = can_offload(pair, chain, g)
#                print("offload_route: %s" % offload_route)
                if len(offload_route)>0:
                    if chain_module.index(chain) not in offload_option:
                        offload_option[chain_module.index(chain)] = []
                    offload_option[chain_module.index(chain)].extend(offload_route)
#    print("offload_options: %s" % offload_option)
    offload_case = {}
    for key in offload_option:
#        print("KEY: %s" % key)
        chain_copy = copy.deepcopy(chain_module[key])
        chain_bess, _ = placeTool.bfs_sort(chain_copy)
        route_list = offload_option[key]
        route_list = sorted(route_list,key = len, reverse=True)
#        print("sorted route: %s" % route_list)
        for route in route_list:
#            print("CURRENT ROUTE: %s" % route)
            chain_another_copy = copy.deepcopy(chain_module[key])
            is_NR = False
            target_subgroup = []
            for index in route:                
                for subgroup in chain_bess:
                    if chain_another_copy[index] in subgroup:
                        if subgroup not in target_subgroup:
                            target_subgroup.append(subgroup)
                chain_another_copy[index].nf_type = 1
            chain_new_copy = copy.deepcopy(chain_another_copy)
            chain_bess_after, _ = placeTool.bfs_sort(chain_another_copy)
            target_subgroup = []
            for subgroup in chain_bess_after:
#                print("type of route[0]: %s" % type(route[0]))
#                print("Length of chain_another_copy: %s" % (len(chain_new_copy)))
                if chain_new_copy[route[0]] in subgroup:
                    target_subgroup = subgroup
            for module in target_subgroup:
                if module.nf_class in dup_avoid_list:
                    is_NR = True
            left_vector, right_const = placeTool.inequal_form(target_subgroup, len(chain_module), para_list)
            left_value = max(left_vector)
            if is_NR:
#                print("key %s route %s: value %s" % (key, route, right_const/float(left_value)))
                if not placeTool.not_satisfy_rate(right_const/float(left_value), chain_rate[key], True):
#                    print("FIND ROUTE: KEY %s ROUTE %s" % (key, route))
                    record_solution = False
                    if strict_flag:
                        chain_separate_copy = copy.deepcopy(chain_module[key]) 
                        chain_before = copy.deepcopy(chain_bess)
                        throughput_subset_vector = []
                        for subset in chain_before:
                            left_subset_vector, right_subset_const = placeTool.inequal_form(subset, len(chain_module), para_list)
                            left_subset_value = max(left_subset_vector)
                            throughput_subset_vector.append(right_subset_const/float(left_subset_value))
                            throughput_subset_before = min(throughput_subset_vector)
                            if throughput_subset_before<= right_const/float(left_value):
                                record_solution = True
                    else:
                        record_solution = True
                    if record_solution:
                        if key not in offload_case:
                            offload_case[key] = []
                        offload_case[key].append(route)
            else:
                throughput_before = []
                two_subgroup = []
                chain_additional_copy = copy.deepcopy(chain_module[key])
                before_copy = copy.deepcopy(chain_bess)
#                print("COMES HERE")
                for subgroup_before in before_copy:
                    if chain_additional_copy[route[0]] in subgroup_before or chain_additional_copy[route[-1]] in subgroup_before:
                        if subgroup_before not in two_subgroup:
                            two_subgroup.append(subgroup_before)
                for each_subgroup in two_subgroup:
                    each_left_vector, each_right_const = placeTool.inequal_form(each_subgroup, len(chain_module), para_list)
                    each_left_value = max(each_left_vector)
                    throughput_before.append(each_right_const/float(each_left_value))
#                print("throughput_before: %s" % throughput_before)
#                print("calculated new: %s" % (2*(right_const/float(left_value))))
                if 2*(right_const/float(left_value)) > min(throughput_before):
                    if key not in offload_case:
                        offload_case[key] = []
                    offload_case[key].append(route)
    for key in offload_case:
        route_list  = copy.deepcopy(offload_case[key])
#        print("chain %s resulted route list: %s" % (key, route_list))
        init_list = []
        first = route_list.pop(0)
        init_list.append(first)
#        print("route_list: %s" % route_list)
#        print("init_list: %s" % init_list)
        for route in route_list:
#            print("Length of route_list: %s" % len(route_list))
            for exist_set in init_list:
#                print("exist_set: %s" % set(exist_set))
#                print("route: %s" % set(route))
                if exist_set == route:
                    if (set(exist_set) & set(route)):
                        init_list.append(route)
                    else:
                        exist_set = exist_set + route
        init_list = sorted(init_list, key=len, reverse=True)
        decided_route = init_list.pop(0)                
        for index in decided_route:
            chain_module[key][index].nf_type = 1
    final_list = []
    for chain in chain_module:
        final_list = final_list + chain
#    placeTool.log_module(final_list)

#    return module_list   
    return final_list

def next_smaller_bounce_placement(module_list):
    copy_module_list = copy.deepcopy(module_list)
    chain_module, _ = placeTool.segment_module_list(copy_module_list)
    offload_option = {}
    offload_throughput = {}
    para_list,_ = placeTool.read_para()
    for chain in chain_module:
        g = get_graph(chain)
        chain_copy = copy.deepcopy(chain)
        chain_bess, chain_p4 = placeTool.bfs_sort(chain_copy)
#        dup_num, dup_list, no_dup_list = placeTool.count_dup(0, range(len(chain_bess)), chain_bess)
#        updated_chain_bess = copy.deepcopy(dup_list)
        updated_chain_bess = copy.deepcopy(chain_bess)
        if len(updated_chain_bess)>1:
            for pair in itertools.combinations(updated_chain_bess, 2):
                offload_route = can_offload(pair, chain, g)
                if len(offload_route)>0:
                    if chain_module.index(chain) not in offload_option:
                        offload_option[chain_module.index(chain)] = []
                    offload_option[chain_module.index(chain)].extend(offload_route)
#    print("offload_option: %s" % offload_option)
    for key in offload_option:
        chain_copy = copy.deepcopy(chain_module[key])
        chain_bess, _ = placeTool.bfs_sort(chain_copy)
        subgroup_throughput = []
        for subgroup in chain_bess:
            left_vector, right_const = placeTool.inequal_form(subgroup, len(chain_module), para_list)
            left_value = max(left_vector)
            subgroup_throughput.append(right_const/float(left_value))
        throughput_before = min(subgroup_throughput)
        for route in offload_option[key]:
            chain_another_copy = copy.deepcopy(chain_module[key])
            for index in route:
                chain_another_copy[index].nf_type = 1
            chain_bess_after, _ = placeTool.bfs_sort(chain_another_copy)
            subgroup_throughput_after = []
            for subgroup in chain_bess_after:
                left_vector, right_const = placeTool.inequal_form(subgroup, len(chain_module), para_list)
                left_value = max(left_vector)
                subgroup_throughput_after.append(right_const/float(left_value))
            throughput_after = min(subgroup_throughput_after)
            delta = throughput_before - throughput_after
            if key not in offload_throughput:
                offload_throughput[key] = []
            offload_throughput[key].append(delta)
#    print("offload_throughput: %s" % offload_throughput)
    if len(offload_throughput) == 0:
        return []
    key, index = least_change(offload_throughput)
    offload_bounce = offload_option[key][index]
#    print("chosen chain %s bounce: %s" % (key, offload_bounce))
    for module_index in offload_bounce:
        chain_module[key][module_index].nf_type = 1
    final_list = []
    for chain in chain_module:
        final_list = final_list + chain
#    log_module(final_list)
#    print("length of left modules: %d" % (len(final_list)))
    return final_list

def heuristic_main():

#    print("last index:%s" % last_index)
    #parse_user_configuration_chain
    global bess_module_list, p4_module_list, p4_14_module_list, dup_avoid_list
    global CONF_LIB, P414_LIB_DIR, P416_LIB_DIR, OUTPUT_DIR
    global error_rate

    print("List all user-level configuration scripts:")
    subprocess.call(['ls', './user_level_examples'])

    arg_parser = get_argparse()
    args = arg_parser.parse_args()
    enumerate_bool = args.iter
    of_flag = args.of
    p4_version = args.lang[0]
    op_mode = args.mode
    input_filename = args.file

    config_filename = './user_level_examples/'+input_filename+'.conf'
    entry_filename = input_filename
    p4_code_name = "heuristic"
    final_p4_filename = os.path.join(OUTPUT_DIR, p4_code_name.strip() + ".p4")
    final_bess_filename = os.path.join(OUTPUT_DIR, p4_code_name.strip() + ".bess")

    """
    Handle OpenFlow case    
    """
    of_module = {
#        'ACL': 'acl.lib',
        'IPv4Forward': 'ipv4_forward.lib',
        'VLANPush': 'vlan_add.lib',
        'VLANPop': 'vlan_rm.lib',
#        'HashLB':'hash_lb.lib'    
        }
    if of_flag:
        ND.p4_module_list = of_module
        ND.p4_14_module_list = of_module
    print('NFCP ConfParser is running...')
    conf_parser = configParser.nfcp_config_parser(config_filename)
    for flowspec_name, nfchain_name in conf_parser.scanner.flowspec_nfchain_mapping.items():
        chain_ll_node = conf_parser.scanner.struct_nlinkedlist_dict[nfchain_name]
        flowspec_instance = conf_parser.scanner.struct_nlist_dict[flowspec_name]
        #p4_logger.info(" -flow[%s]: %s\n" %(flowspec_name, flowspec_instance))
        # Print all pipelines to the NFCP users
        print(chain_ll_node._draw_pipeline())
        pipeline_fp = open(('_pipeline.txt'), 'a+')
        pipeline_fp.write(chain_ll_node._draw_pipeline())
        pipeline_fp.close()

    nf_node_list = parse_all_node(conf_parser)
    weight_dict = placeTool.generate_weight(nf_node_list)
    nf_node_list = placeTool.tag_weight(nf_node_list, weight_dict)
    node_list = init_allp4(nf_node_list)
    # test functionality
#    node_list = next_smaller_bounce_placement(node_list)
#    examine_prev(node_list)
    
    state = STATE_INIT
    find_solution = False
    stop_search = False
    candidate_list = []

    while(not stop_search):
        
        if state == 0: 
#            success = fitp4(conf_parser, node_list, final_p4_filename, p4_version)
            success = True
            if success: state = 1.5
            else:  state = 1                   

        elif state == 1: 
            node_list = next_placement_to_offload_p4(node_list)
            if(len(node_list) != 0):  state = 0
            else:  state = 5

        elif state == 1.5:
            candidate_list.append(copy.deepcopy(node_list))
            advanced_list = potential_better_placement(node_list, False)
            candidate_list.append(advanced_list)
            strict_advanced_list = potential_better_placement(node_list, True)
            candidate_list.append(strict_advanced_list)
            if(len(candidate_list)!=0):  state = 2
            else: state = 5
            
        elif state == 2: 
            new_candidate_list = []
            throughput_list = []
            satisfy_SLO = False
            for case_list in candidate_list:
                SLO_result, case_list, estimate_throughput = highest_core_allocation_derived_from_LP(case_list)
                if SLO_result:
                    satisfy_SLO = True
                new_candidate_list.append(case_list)
                throughput_list.append(estimate_throughput)
            if satisfy_SLO: 
                get_index = throughput_list.index(max(throughput_list))
                node_list = new_candidate_list[get_index]
                print("throughput_list: %s, get_index: %s" % (throughput_list, get_index))
                print(colored(str(max(throughput_list)), 'red'))
                state = 4
            else:  
                node_list = new_candidate_list[0]
                state = 3
                    
        elif state == 3: 
            node_list = next_smaller_bounce_placement(node_list)
            candidate_list = []
            candidate_list.append(node_list)
            if(len(node_list) != 0):  state = 2
            else:  state = 5
                    
        elif state == 4: 
            find_solution = True
            stop_search = True
                    
        elif state == 5: 
            stop_search = True
        
    

    if find_solution: 
#        log_module(node_list)
        if not of_flag:
            output_list = copy.deepcopy(node_list)
            final_output_code = generate_code(conf_parser, node_list, final_p4_filename, p4_version)
        else:
            output_list = []
        bess_code(conf_parser, node_list, final_bess_filename)
        return output_list
    else:
        print('cannot find solution')
        return []

def get_module_info(node_list):
    module_info = []
    for module in node_list:
        module_info.append([module.nic_index, module.core_num])
    return module_info


def error_call():    
    standard_result = heuristic_main()
    default_info = get_module_info(standard_result)
    final_result = []
    for i in range(21):
        error_percent = (i-10)/100.0
        placeTool.error_rate = error_percent
        compare_result = heuristic_main()
        compare_info = get_module_info(compare_result)
        if(compare_info == default_info):
            final_result.append([error_percent,"SAME"])
        elif compare_info == list():
            final_result.append([error_percent,"INVALID"])
        else:
            final_result.append([error_percent,"Different"])
    for item in final_result:
        print(colored(item, 'blue'))

def target_compare():
#    heuristic_main()
    placeTool.error_rate = 0.09
    heuristic_main()

if __name__ == "__main__":
    heuristic_main()