'''
NF_PLACEMENT.PY
This python code is used to decide NF placement.
'''
import warnings
import os
import logging
import itertools
import math
import copy
import re
import json
import time
import ast
import random
import numpy as np
from ast import literal_eval as make_tuple
from user_level_parser.UDNFCPUserListener \
    import convert_nf_graph, convert_global_nf_graph
from collections import OrderedDict, defaultdict
from operator import itemgetter
from optimization import maximizeMarginalRate, marginalRate


PLACE_LOGGER = logging.getLogger("placement_logger")
PLACE_LOGGER.setLevel(logging.DEBUG)

FH = logging.FileHandler('placement.log')
FH.setLevel(logging.DEBUG)
FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
FH.setFormatter(FORMATTER)

PLACE_LOGGER.addHandler(FH)

global error_rate

error_rate = 0
BOUNCE_TIME = 12*1700/2
BASE_CYCLE = 204
RESERVE_CORE = 2
MAX_THROUGHPUT = 6400000000
CPU_FREQ = 1700000000
PKT_SIZE = 1500*8
FREQ = 1700

def read_para():
    '''
    This func reads the content of FILE 'module_data.txt'.
    It is used to parse the profile number of each BESS
    module and keep (BESS_module_class, required_cycles)
    in a dictionary 'bess_para.' A special profile number
    called 'constraints' is the number of available cores.
    The return values are 'bess_para' dictionary and 
    'constraints'.
    '''
    bess_para = {}
    constraints_all = {}
    fp = open('module_data.txt', 'r')
    for line in fp:
        information = line.split()
        if information:
            assert len(information) == 3
            if information[0].lower() == 'bess':
                bess_para[information[1]] = information[2]
            else:
                warnings.warn('Warning: unrecognized device info or using p4 module')
    PLACE_LOGGER.debug("read-in info bess module: %r", bess_para)
    constraint = bess_para.get("constraints")
    if constraint:
        constraints_all['bess_core'] = int(constraint)
    return bess_para, constraints_all

def enum_case(module_list):
    '''
    This func would enum all possible cases for a chain.
    The input would be a module list belonging to a chain.
    The output would be enum cases which asserts
    '''
    num_bit = len(module_list)
    option_count = 0
    enum_list = []

    for module in module_list:
        if module.is_both():
            option_count += 1
    if option_count>0:
        total_case = (1<<option_count)
    else:
        total_case = 0

    for case_num in range(total_case):
        pattern = 0
        case_num_copy = case_num
        for module in module_list:
            pattern = (pattern<<1)
            if module.is_both():
                pattern += case_num_copy % 2
                case_num_copy = case_num_copy>>1
            elif module.is_bess():
                pattern += 1
        enum_list.append(pattern)

    if option_count == 0:
        pattern_none = 0
        for module in module_list:
            pattern_none = (pattern_none<<1)
            if module.is_bess():
                pattern_none += 1
        enum_list.append(pattern_none)

    return enum_list

def find_max(module_list, module, pattern, para_list):
    '''
    Given module list, profile number and target pattern as input, 
    this func recursively calculates the max cycles of a chain.
    The final return value is the max cycle of a chain and it is 
    used to proportionally estimate the throughput.
    '''
    value = 0
    #PLACE_LOGGER.debug("find_max: %s", module)
    ref = module_list.index(module)
    mode_bit = (pattern>>(len(module_list)-ref-1))%2
    return_module = None
    if mode_bit:
        core_num = module.core_num
 #       print(module.nf_class+ para_list.get(str(module.nf_class))+ " core num "+ str(core_num))
        if module.core_num >=2:
            core_num = module.core_num -1
        if int(para_list.get(str(module.nf_class))) < BASE_CYCLE:
            core_num = 1
        value = int(para_list.get(str(module.nf_class)))/core_num
    else:
        value = 0
    
    latest_max = 0
    for child in module.adj_nodes:
        value_child, max_value, get_module = \
            find_max(module_list, child, pattern, para_list)
        latest_max = max(latest_max, max_value/len(module.adj_nodes))
        if latest_max == (max_value/len(module.adj_nodes)):
            return_module = get_module
        value = int(value) + (value_child/len(module.adj_nodes))
        latest_max = max(latest_max, value)
        if latest_max == value:
            return_module = module

    return value, latest_max, return_module

def notate_list(target_list, bess_core, mask_pattern):
    '''
    Given list of module, this func changes the number of cores for
    each BESS module according to input 'bess_core' assignment. By 
    changing the number of cores, it represents the module within a
    subgroup would be duplicated for how many copies. 
    '''
    start_index = 0
    flip_bit = False
    skip = False
    last_assign_core = 1
    for module in target_list:
        ref = target_list.index(module)
        mode_bit = (mask_pattern>>(len(target_list)-ref-1))%2
        module.nf_type = mode_bit
        if module.is_branch_node():
            skip = True
        elif module.is_merge():
            skip = False
        if not skip and not module.is_dup_avoid():
            ref = target_list.index(module)
            mode_bit = (mask_pattern>>(len(target_list)-ref-1))%2
            if flip_bit^mode_bit:
                flip_bit = not flip_bit
                if mode_bit:
                    if bess_core[start_index]>2:
                        module.core_num = bess_core[start_index]
                        last_assign_core = bess_core[start_index]
                        start_index += 1
            else:
                if mode_bit:
                    module.core_num = last_assign_core
        elif module.is_dup_avoid():
            flip_bit = False
    return target_list

def segment_module_list(all_modules):
    '''
    This func is used to segment a huge list of modules into several
    sub-lists of modules, where each sub-list contains the modules of
    a certain chain. Thus, this func gets a huge list 'all_modules' as
    input and output a list of lists.
    '''
    cut_index = []
    start = 0
    chain_module_list = []
    for module in all_modules:
        if len(module.adj_nodes)==0:
            cut_index.append(all_modules.index(module))
#            print "module.time", module.time
    for index in cut_index:
        module_list = all_modules[start: index+1]
        start = index+1
        chain_module_list.append(module_list)
    return chain_module_list, cut_index

def no_core_op_calc_cycle(pattern_list, module_list, bess_para):
    '''
    This func is to calculate the throughput of no_core_optimization
    algorithm. This algorithm does not consider duplicate modules, so
    there is no phase-2, i.e. packing phase involved. The return value
    is a dictionary of <pattern, throughput>.
    '''
    nic = get_nic_info()
    avail_nic_num = len(nic["nic"])
    pattern_throughput_dict = []
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)
    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    for pattern in pattern_list:
        if pattern == 0:
            module_info = []
            for module in module_list:
                module_info.append([module.nic_index, module.core_num]) 
            pattern_throughput_dict.append([0, module_info, MAX_THROUGHPUT])
        else:
            pattern_binary = "{0:b}".format(pattern)
            tmp_tuple_list = [1]*pattern_binary.count('1')
            ones_tuple = tuple(tmp_tuple_list)
            module_list_backup = copy.deepcopy(module_list)
            total_module_num = len(module_list)
            for module_index in range(total_module_num):
                mode_bit = (pattern>>(total_module_num - module_index-1))%2
                module_list_backup[module_index].nf_type = mode_bit
                if mode_bit == 1:
                    module_list_backup[module_index].nic_index = 0
#            notate_module_list = notate_list(module_list_backup, ones_tuple, pattern)
            notate_module_list = module_list_backup
            cp_final_module = copy.deepcopy(notate_module_list)

            bess_subgroup_list, p4_list = bfs_sort(notate_module_list)
            left_matrix = []
            right_matrix = []
            for sub_list in bess_subgroup_list:
                left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
                left_matrix.append(left_vector)
                right_matrix.append(right_const)
            sum_of_left_traffic = [0]*total_chain_num
            sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
            left_matrix.append(sum_of_left_traffic)
            right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
            left_matrix = np.array(left_matrix)
            right_matrix = np.array(right_matrix)
            t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
            mr =  marginalRate(chain_rate, t)
            no_record = False
            if sum(list(t)) == 0:
                no_record = True
            if not no_record:
                core_num_all = []
                for module in cp_final_module:
                    core_num_all.append([module.nic_index, module.core_num])
                pattern_throughput_dict.append([pattern, core_num_all, mr, sum(mr)])
    '''
    pattern_len = len(module_list)
    pattern_cycle_dict = []
    cut_index = []
    for module in module_list:
        if len(module.adj_nodes) == 0:
            cut_index.append(module_list.index(module))
    for pattern in pattern_list:
        print pattern
        start = -1
        total_throughput = 0
        for index in cut_index:
            max_cycle = 0
            mask_pattern = ((pattern&((1<<(pattern_len-start-1))-1))>>(pattern_len-index-1))
            tmp_module_list = copy.deepcopy(module_list[start+1:index+1])
            _, max_cycle, get_module = find_max(tmp_module_list, tmp_module_list[0], mask_pattern, bess_para)
            if max_cycle == 0:
                max_cycle = 0.01
            total_throughput = total_throughput + math.log10(1/float(max_cycle))
            start = index
        pattern_cycle_dict.append([pattern, total_throughput])
    print pattern_cycle_dict
    '''
    return pattern_throughput_dict

def dup_able_count(pattern, chain_module):
    '''
    This func is to calculate how many subgroups can be duplicated in A chain.
    A subgroup is formed when a continuous group of BESS modules are bounded
    by P4 modules. The cautions are some modules are not able to be duplicated
    that are marked to be 'dup_avoid' and branches are not allowed to be
    duplicated.
    '''
    flip_bit = False
    chain_len = len(chain_module)
    subgroup_num = 0
    skip = False
    for i in range(len(chain_module)):
        if chain_module[i].is_branch_node():
            skip = True
        elif chain_module[i].is_merge():
            skip = False
        if not skip and not chain_module[i].is_dup_avoid():
            mode_bit = (pattern>>(chain_len-i-1))%2
            if mode_bit^flip_bit:
                flip_bit = not flip_bit
                if mode_bit:
                    subgroup_num += 1
        elif chain_module[i].is_dup_avoid():
            flip_bit = False
    return subgroup_num

def count_subgroup_num(pattern, module_list):
    '''
    This func is to calculate how many subgroups exist among chains.
    It utilizes dup_able_count func to calculate the number for each
    chain and then aggregate the total subgroup number. The output is
    a list of subgroup count for each chain.
    '''
    cut_index = []
    pattern_len = len(module_list)
    subgroup_count_list = []
    for module in module_list:
        if len(module.adj_nodes) == 0:
            cut_index.append(module_list.index(module))
    start = -1
    subgroup_count = 0
    for index in cut_index:
        mask_pattern = ((pattern&((1<<(pattern_len-start-1))-1))>>(pattern_len-index-1))
        tmp_module_list = copy.deepcopy(module_list[start+1:index+1])
        subgroup_count_list.append( dup_able_count(mask_pattern, tmp_module_list))
        start = index
    return subgroup_count_list

def calc_addition(pattern, cut_index, pattern_len):
    '''
    For calculation of how many spare cores for duplication usage,
    we preserve two cores for each chain head, but some chain might
    be fit into P4 without any BESS modules. Thus, this func is to 
    calculate how many cores can actually be retrieved back from
    preservation to be used as spare cores.
    '''
    target_num = 0
    start = -1
    for index in cut_index:
        mask_pattern = ((pattern&((1<<(pattern_len-start-1))-1))>>(pattern_len-index-1))
        if int(mask_pattern) == int(0):
            target_num += 1
        start = index
    return target_num

def not_satisfy_rate(test, restrict, min_only_bool):
    #condition_bool = False
    if min_only_bool:
        return test<int(restrict[0])
    else:
        if test<int(restrict[0]) or test>int(restrict[1]):
    #    print("failed case:", test_cycle, restrict_cycle[0], restrict_cycle[1]) 
            return True
        else:
            return False

def get_rate():
    rate = []
    fp = open("chain_rate.txt",'r')
    for line in fp:
        content = line.split()
        new_list = []
        for number in content:
            new_list.append(float(number))
        rate.append(tuple(new_list))
    rate = tuple(rate)
#    print(rate)
    return rate

def get_nic_info():
    with open('device.txt') as f:
        data = json.load(f)
    return data

def get_delay():
    fp = open("max_delay.txt", 'r')
    delay_ls = []
    for line in fp:
        delay_ls.append(float(line)*FREQ)
#    print "read in delay constraint:", delay_ls
    return delay_ls

def bfs_sort(module_list):
    p4_list = []
    bess_list = []
    queue_bess = []
    while len(module_list)>0:
        module = module_list.pop(0)
        if module.is_p4() or module.is_smartnic():
            p4_list.append(module)
        else:
            insert_index = -1
            queue_bess.append(module)
            while len(queue_bess)>0:
                sub_module = queue_bess.pop(0)
                for i in range(len(bess_list)):
                    if sub_module in bess_list[i]:
                        insert_index = i
                        break
                if insert_index > -1:
                    break
            if insert_index == -1:
                bess_list.append([])
            queue_bess.append(module)
            while len(queue_bess)>0:
                sub_module = queue_bess.pop(0)
                for index in range(len(bess_list)-1):
#                    print "index", index, "length of bess_list", len(bess_list)
                    if sub_module in bess_list[index]:
                        insert_index = index
                        last_insert = bess_list.pop(-1)
                        bess_list[index].extend(last_insert)
                        break
                if sub_module.is_bess() and sub_module not in bess_list[insert_index]:
                    bess_list[insert_index].append(sub_module)
                    if sub_module in module_list:
                        module_list.remove(sub_module)
                    for child in sub_module.adj_nodes:
                        queue_bess.append(child)
    return bess_list, p4_list 

def count_dup(nic_index, list_index, bess_subgroup_list):
    dup_num = len(list_index)
    dup_list = []
    no_dup_list = []
    for index in list_index:
        dup_bool = True
        sub_list = bess_subgroup_list[index]
        for module in sub_list:
#            print module.nf_class, "in count_dup", module.parent_count
            module.nic_index = nic_index
        for module in sub_list:
            if module.is_dup_avoid() or module.is_branch_node() or len(module.prev_nodes)>1:
                dup_num -= 1
                dup_bool = False
                break
        if dup_bool:
            dup_list.append(copy.deepcopy(sub_list))
        else:
            no_dup_list.append(copy.deepcopy(sub_list))
    return dup_num, dup_list, no_dup_list

def tag_core(dup_list, dup_tuple):
    for i in range(len(dup_list)):
        for module in dup_list[i]:
            module.core_num = 1+dup_tuple[i]
            if module.core_num <1:
                print "HAPPENING HERE"
    return dup_list

def tag_chain_index(module_list):
    index_ptr = 1
    for module in module_list:
        module.chain_index = index_ptr
        if len(module.adj_nodes)==0:
            index_ptr+=1
#        print("module_chain_index: ", module.chain_index)
    return module_list

def tag_core_index(subgroup):
    default_value = 0
    queue_a = []
    return_subgroup = []
    cp_subgroup = copy.deepcopy(subgroup)
#    print "before tag:", len(subgroup)

    while len(cp_subgroup)>0:
        module = cp_subgroup.pop(0)
        assert module.is_bess()
        queue_a.append(module)
        while len(queue_a)>0:
            target_module = queue_a.pop(0)
            for adj_node in target_module.adj_nodes:
                if len(adj_node.prev_nodes) < 2 and adj_node in cp_subgroup:
                    queue_a.append(adj_node)
            if target_module in cp_subgroup:
                cp_subgroup.remove(target_module)
            target_module.core_index = default_value
            return_subgroup.append(target_module)
        default_value += 1
    return_subgroup.sort(key=lambda l: (l.service_path_id, l.service_id))
#    for module in return_subgroup:
#        print module.nf_class, " core index", module.core_index
#    print "after tag:", len(return_subgroup)
    return return_subgroup

def tag_weight(module_list, weight_dict):
    head = True
    for module in module_list:
        if head:
            module.weight = 1
            head = False
        else:
            module.weight = 0
        if len(module.adj_nodes) == 0:
            head = True
    for i in range(len(module_list)):
        for adj_node in module_list[i].adj_nodes:
#            adj_node.parent_count += 1
            index_str = "W%d%d%d%d" % (module_list[i].service_path_id, module_list[i].service_id,\
                adj_node.service_path_id, adj_node.service_id)
            adj_node.weight = adj_node.weight + module_list[i].weight*weight_dict[index_str]
    return module_list

def tag_from_notated_list(module_list, notated_list):
    '''
    Tagged from the copy list and tag string weight
    '''
    '''
    head = True
    for module in module_list:
        if head:
            module.weight = 1
            head = False
        else:
            module.weight = 0
        if len(module.adj_nodes) == 0:
            head = True
    '''
#        print("Before changes: %s %.10f" % (module.nf_class, module.weight))
    for i in range(len(module_list)):
        module_list[i].core_num = notated_list[i].core_num
        module_list[i].nic_index = notated_list[i].nic_index
        module_list[i].chain_index = notated_list[i].chain_index
        module_list[i].nf_type = notated_list[i].nf_type
        module_list[i].core_index = notated_list[i].core_index
#        print("%s %.10f" % (module_list[i].nf_class, module_list[i].weight))
        '''
        for adj_node in module_list[i].adj_nodes:
            index_str = "W%d%d%d%d" % (module_list[i].service_path_id, module_list[i].service_id,\
                adj_node.service_path_id, adj_node.service_id)
            adj_node.weight = adj_node.weight + module_list[i].weight*weight_dict[index_str]
#            print("adj_node.weight %d, add value %d" % (adj_node.weight, module_list[i].weight*weight_dict[index_str]))
        '''
    return module_list

def generate_weight(module_list):
    weight_dict={}
    module_list.sort(key=lambda l: (l.service_path_id, l.service_id))
    for i in range(len(module_list)):
        for adj_node in module_list[i].adj_nodes:
            transition_str = "W%d%d%d%d" % (module_list[i].service_path_id, module_list[i].service_id,\
                        adj_node.service_path_id, adj_node.service_id)
            weight_dict[transition_str] = int(1)/float(len(module_list[i].adj_nodes))
#            print("transition %s value %.10f" % (transition_str, weight_dict[transition_str]))
#    print(weight_dict)
    return weight_dict

def err_add(number, percentage):
#    error_percent = random.uniform(0-percentage, percentage)
    return number*(1+percentage)

def inequal_form(sub_list, total_chain_num, para_list):
    global error_rate
    return_vector = [0]*total_chain_num
    return_weight = 0
    str_list = []
    end_node_queue = []
    traffic = 0
    right_index_dict = {}
    for module in sub_list:
        core_num = module.core_num
        if module.core_num <1:
            print "warning", module.nf_class
        str_list.append("%d%d" % (module.service_path_id, module.service_id))
#        print "discovered core index", module.core_index
        if module.core_index not in right_index_dict:
            right_index_dict[module.core_index] = 0
#        print module.nf_class
        right_index_dict[module.core_index] += module.weight*err_add(int(para_list.get(str(module.nf_class))),error_rate)/float(core_num)
#        return_weight += module.weight*int(para_list.get(str(module.nf_class)))/float(core_num)
    for module in sub_list:
        add_to_queue = True
        for adj_node in module.adj_nodes:
            add_to_queue = True
            cmp_str = "%d%d" % (adj_node.service_path_id, adj_node.service_id)
            if cmp_str in str_list:
                add_to_queue = False
            if add_to_queue and module not in end_node_queue:
                end_node_queue.append(copy.deepcopy(module))
    for node in end_node_queue:
        child_num = 0
        for child in node.adj_nodes:
            if child not in sub_list:
                child_num+=1
        traffic += node.weight*child_num/(len(node.adj_nodes))
    
    return_vector[sub_list[0].chain_index-1] = traffic
    right_vector = []
    for key in right_index_dict:
        right_vector.append(right_index_dict[key])
    bottleneck_cycle = max(right_vector)
    return_weight = CPU_FREQ/float(bottleneck_cycle)*PKT_SIZE
#    return_weight = CPU_FREQ/float(return_weight)*PKT_SIZE
    return return_vector, return_weight

def calc_delay(module_list, para_list):
    root_type = 0
    root_bool = True
    for module in module_list:
        if root_bool:
            if module.is_bess():
                module.time = BOUNCE_TIME
            else:
                module.time = 0
            root_bool = False
        for adj_node in module.adj_nodes:
            mypass = module.time
            if module.is_bess():
                mypass += int(para_list.get(str(module.nf_class)))
            else:
                mypass += 0
            if adj_node.nf_type != module.nf_type:
                mypass = mypass+BOUNCE_TIME
            adj_node.time = max(adj_node.time, mypass)
        if len(module.adj_nodes)==0:
            root_bool = True
    return module_list

def verify_time(module_list):
    end_of_node_time = []
    for module in module_list:
        if len(module.adj_nodes) == 0:
            end_of_node_time.append(module.time)
    delay_ls = get_delay()
    success_bool = True
    for index in range(len(delay_ls)):
#        print "chain ", index, "delay constraint: ", delay_ls[index], "compute time:", end_of_node_time[index]
        if delay_ls[index] < end_of_node_time[index]:
            success_bool = False
    return success_bool, end_of_node_time
    

def speed_up_calc_cycle(pattern_list, module_list, bess_para, constraints):
    nic = get_nic_info()
    avail_nic_num = len(nic["nic"])
    pattern_throughput_dict = []
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)

    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    spare_core = int(nic["nic"][0]["core"])-RESERVE_CORE
    #print "pattern", pattern_list
    print "Length of pattern:", len(pattern_list) 
    pattern_counter = 0
    for pattern in pattern_list:
#        print "pattern", pattern
        if pattern_counter%10 == 0:
            print "handling ", pattern_counter, " pattern"
        pattern_counter += 1
        pattern_start = time.time()
        usable_core = spare_core
        if pattern == 0:
            module_info = []
            for module in module_list:
                module_info.append([module.nic_index, module.core_num]) 
            pattern_throughput_dict.append([0, module_info, MAX_THROUGHPUT])
        else:
            pattern_binary = "{0:b}".format(pattern)
#            print pattern_binary
            tmp_tuple_list = [1]*pattern_binary.count('1')
            ones_tuple = tuple(tmp_tuple_list)
            module_list_backup = copy.deepcopy(module_list)
            notate_module_list = notate_list(module_list_backup, ones_tuple, pattern)
            notate_module_list = calc_delay(notate_module_list, bess_para)
            time_bool, end_of_node_time = verify_time(notate_module_list)

            if not time_bool:
#                print "UNQUALIFY"
                continue

            chain_module_list, _ = segment_module_list(notate_module_list)
            infeasible = False
            final_module = []
            final_dict = []

            for chain_index in range(total_chain_num):
#                print "chain_index", chain_index, " usable_core:", usable_core
                chain_success = False
                chain_bess, chain_p4 = bfs_sort(copy.deepcopy(chain_module_list[chain_index]))
                if len(chain_bess) == 0:
                    final_module.extend(chain_p4)
                    chain_success = True
                else:
                    for i in range(len(chain_bess)):
                        subgroup = chain_bess[i]
                        chain_bess[i] = tag_core_index(subgroup)
                    dup_num, dup_list, no_dup_list = count_dup(0, range(len(chain_bess)), chain_bess)
                    bool_tag = []
                    for no_dup_sublist in no_dup_list:
                        left_vector, right_const = inequal_form(no_dup_sublist, len(chain_module_list), bess_para)
                        left_value = max(left_vector)
                        if (right_const/float(left_value) < chain_rate[chain_index][0]): 
#                            log_module(no_dup_sublist)
#                            print("BUGGGGGG? right_const: %d left_value: %d" % (right_const, left_value))
                            infeasible = True
                        else:
                            usable_core -= 1

                    for dup_sublist in dup_list:
                        left_vector, right_const = inequal_form(dup_sublist, len(chain_module_list), bess_para)
                        left_value = max(left_vector)
                        if not_satisfy_rate(right_const/float(left_value), chain_rate[chain_index], True):
                            used_core = math.ceil(chain_rate[chain_index][0]*float(left_value)/right_const)
#                            print"used_core: ", used_core
                            if used_core > usable_core:
                                infeasible = True
                            else:
                                usable_core = usable_core - used_core
                                dup_sublist = tag_core([dup_sublist], tuple([used_core-1]))
                                chain_success = True
                        else:
                            usable_core = usable_core - 1
                            chain_success = True
                        if right_const/float(left_value) > chain_rate[chain_index][1]:
                            bool_tag.append(False)
                        else:
                            bool_tag.append(True)
                    if dup_num == 0:
                        chain_success = True
                    if chain_success:
                        for no_dup_sublist in no_dup_list:
                            final_module.extend(no_dup_sublist)
                        for index in range(len(dup_list)):
                            if bool_tag[index]:
#                                print dup_list[index][0].nf_class
                                final_dict.append(dup_list[index])
                            else:
                                final_module.extend(dup_list[index])
                        final_module.extend(chain_p4)
            pattern_preallocate_end = time.time()
            if not infeasible:
#                feasible_start = time.time()
                if len(final_dict)>0 and usable_core>0:

#                    rng = list(range(int(usable_core)+1))*len(final_dict)
#                    core_iter = itertools.permutations(rng, len(final_dict))
                    core_iter = itertools.combinations_with_replacement(list(range(len(final_dict))), int(usable_core))
                    core_dict = []
                    for core_tuple in core_iter:
#                        core_start = time.time()
                        tmp_ls = []
#                        print "core_tuple before", core_tuple
                        for index in range(len(final_dict)):
                            tmp_ls.append(core_tuple.count(index))
                        core_tuple = tuple(tmp_ls)
#                        print core_tuple
                        cp_final_dict = copy.deepcopy(final_dict)
                        if core_tuple in core_dict:
                            continue
                        else:
                            core_dict.append(core_tuple)
#                        print "core_tuple", core_tuple
                        if sum(core_tuple) == usable_core:
                            cp_final_module = copy.deepcopy(final_module)
                            cp_final_module.sort(key=lambda l: (l.service_path_id, l.service_id))
                            core_tuple = list(core_tuple)
                            for i in range(len(cp_final_dict)):
                                bottleneck_core = cp_final_dict[i][0].core_num
                                core_tuple[i]= core_tuple[i]+bottleneck_core-1
                            tagged_list = tag_core(cp_final_dict, tuple(core_tuple))
                            for sublist in tagged_list:
                                cp_final_module.extend(sublist)
                            cp_final_module.sort(key=lambda l: (l.service_path_id, l.service_id))
                            tmp_module_list = copy.deepcopy(module_list)
#                            for module in cp_final_module:
#                                print module.nf_class, module.core_num
                            tmp_module_list = tag_from_notated_list(tmp_module_list, cp_final_module)
                            bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
                            left_matrix = []
                            right_matrix = []
                            for sub_list in bess_subgroup_list:
                                left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
                                left_matrix.append(left_vector)
                                right_matrix.append(right_const)
                            sum_of_left_traffic = [0]*total_chain_num
                            sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
                            left_matrix.append(sum_of_left_traffic)
                            right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
#                            print("left matrix", left_matrix)
#                            print("right matrix", right_matrix)
                            left_matrix = np.array(left_matrix)
                            right_matrix = np.array(right_matrix)
                            t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
                            mr =  marginalRate(chain_rate, t)
                            no_record = False
                            if sum(list(t)) == 0:
                                no_record = True
                            if not no_record:
                                core_num_all = []
                                for module in cp_final_module:
                                    core_num_all.append([module.nic_index, module.core_num])
                                pattern_throughput_dict.append([pattern, core_num_all, end_of_node_time, sum(end_of_node_time),  mr, sum(mr)])
                            core_end = time.time()
#                            print "each core iter time", core_end-core_start
#                    feasible_end = time.time()
#                    print "time gap", feasible_end - core_end
#                    print "pattern preallocate", pattern_preallocate_end-pattern_start
#                    print "allocate spare cores", feasible_end - feasible_start
                elif len(final_dict)>0 and usable_core == 0:
#                    print "ever here"
                    cp_final_module = copy.deepcopy(final_module)
#                    print "final_module length:", len(final_module)
#                    print "dup_list length:", len(dup_list)
                    for sublist in final_dict:
                        cp_final_module.extend(sublist)
                    cp_final_module.sort(key=lambda l: (l.service_path_id, l.service_id))
#                    print "length:", len(cp_final_module) 
                    tmp_module_list = copy.deepcopy(module_list)
                    tmp_module_list = tag_from_notated_list(tmp_module_list, cp_final_module)
                    bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
                    left_matrix = []
                    right_matrix = []
                    for sub_list in bess_subgroup_list:
                        left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
                        left_matrix.append(left_vector)
                        right_matrix.append(right_const)
                    sum_of_left_traffic = [0]*total_chain_num
                    sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
                    left_matrix.append(sum_of_left_traffic)
                    right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
                    left_matrix = np.array(left_matrix)
                    right_matrix = np.array(right_matrix)
                    t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
                    mr =  marginalRate(chain_rate, t)
                    no_record = False
                    if sum(list(t)) == 0:
                        no_record = True
                    if not no_record:
                        core_num_all = []
                        for module in cp_final_module:
                            core_num_all.append([module.nic_index, module.core_num])
                        pattern_throughput_dict.append([pattern, core_num_all, mr, sum(mr)])
                elif len(final_dict) == 0:
                    cp_final_module = copy.deepcopy(final_module)
                    cp_final_module.sort(key=lambda l: (l.service_path_id, l.service_id))
                    tmp_module_list = copy.deepcopy(module_list)
                    tmp_module_list = tag_from_notated_list(tmp_module_list, cp_final_module)
                    bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
                    left_matrix = []
                    right_matrix = []
                    for sub_list in bess_subgroup_list:
                        left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
                        left_matrix.append(left_vector)
                        right_matrix.append(right_const)
                    sum_of_left_traffic = [0]*total_chain_num
                    sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
                    left_matrix.append(sum_of_left_traffic)
                    right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
                    left_matrix = np.array(left_matrix)
                    right_matrix = np.array(right_matrix)
                    t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
                    mr =  marginalRate(chain_rate, t)
                    no_record = False
                    if sum(list(t)) == 0:
                        no_record = True
                    if not no_record:
                        core_num_all = []
                        for module in cp_final_module:
                            core_num_all.append([module.nic_index, module.core_num])
                        pattern_throughput_dict.append([pattern, core_num_all, end_of_node_time, sum(end_of_node_time),  mr, sum(mr)])
    return pattern_throughput_dict

def calc_cycle(pattern_list, module_list, bess_para, constraints):
    '''
    This is the main func to calculate estimated proportional throughput
    of all kinds of placement options. This func includes consideration
    of core optimization. The return value is a dictionary of <pattern,
    throughput>.
    '''
    nic = get_nic_info()
    avail_nic_num = len(nic["nic"])
    pattern_throughput_dict = []
    module_list = tag_chain_index(copy.deepcopy(module_list))
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)
#    for module in module_list:
#        print("module class ", module.nf_class, "module chain_index ", module.chain_index)
    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    loop_index = 0
    print "how many pattern in total: ", len(pattern_list)
    for pattern in pattern_list:
        print "loop number: ", loop_index
        success_count = 0
        loop_index += 1
        if pattern == 0:
            none_tuple = tuple([])
            pattern_throughtput_dict.append([0, none_tuple, MAX_THROUGHPUT])
        else:
            pattern_binary = "{0:b}".format(pattern)
 #           print(pattern_binary)
            tmp_tuple_list = [1]*pattern_binary.count('1')
            ones_tuple = tuple(tmp_tuple_list)
            tmp_module_list = copy.deepcopy(module_list)
            notate_module_list = notate_list(tmp_module_list, ones_tuple, pattern)
            bess_subgroup_list, p4_list = bfs_sort(copy.deepcopy(notate_module_list))
            for index in range(len(bess_subgroup_list)):
                subgroup = bess_subgroup_list[index]
                bess_subgroup_list[index] = tag_core_index(subgroup)
            all_subgroup_num = len(bess_subgroup_list)
            nic_place_option = (avail_nic_num)**all_subgroup_num
            for i in range(nic_place_option):
                placement_array = []
                index = i
                for j in range(all_subgroup_num):
                    placement_array.append(index%avail_nic_num)
                    index = index/avail_nic_num
#                print("placement array", placement_array)
                unique_entries = set(placement_array)
                indices = { value : [ i for i, v in enumerate(placement_array) if v == value ] for value in unique_entries }
#                print(indices)
                core_alloc_array = {}
                core_alloc_no_dup = {}
                core_alloc_iter = {}
                for key in indices:
                    core_alloc_array[key] = []
                    core_alloc_no_dup[key] = []
                    dup_num, dup_list, no_dup_list = count_dup(key, indices[key], copy.deepcopy(bess_subgroup_list))
                    core_alloc_array[key] = copy.deepcopy(dup_list)
                    core_alloc_no_dup[key] = copy.deepcopy(no_dup_list)
                    core_alloc_iter[key] = []
                    if dup_num>0:
                        spare_core = int(nic["nic"][int(key)]["core"])-RESERVE_CORE-len(indices[key])
#                        rng = list(range(spare_core+1))*dup_num
#                        core_iter = itertools.permutations(rng, dup_num)
                        core_iter = tuple()
                        if spare_core >0:
                            core_iter = itertools.combinations_with_replacement(list(range(dup_num)), int(spare_core))
                        core_dict = []

                        for core_tuple in core_iter:
                            tmp_ls = []
                            for index in range(dup_num):
                                tmp_ls.append(core_tuple.count(index))
                            core_tuple = tuple(tmp_ls)
                            if sum(core_tuple) == spare_core:
                                core_alloc_iter[key].append(core_tuple)
     
                com_times = 1
                for nic_index in core_alloc_iter:
                    diff_core_num = len(core_alloc_iter[nic_index])
                    if len(core_alloc_iter[nic_index]) == 0:
                        diff_core_num = 1
                    com_times = com_times*diff_core_num
#                    print('com_times', com_times)
                for j in range(com_times):
#                    print("j ", j)
                    notated_final = []
                    chain_locate = {}
                    left_matrix = []
                    right_matrix = []
#                    print("key in core_alloc_iter", core_alloc_iter.keys())
                    for key in core_alloc_iter:
                        chain_locate[key] = []
                        tagged_list = core_alloc_array[key]
                        if len(core_alloc_iter[key]) != 0:                                                 
                            tuple_index = j%len(core_alloc_iter[key])
#                            print(len(core_alloc_iter[key]))
                            core_tuple = core_alloc_iter[key][tuple_index]
                            j = j/len(core_alloc_iter[key])
#                            print "nic_index", key, "assign tuple", core_tuple
                            tagged_list = tag_core(core_alloc_array[key], core_tuple)
                        else:
                            for sub_list_no_assign in core_alloc_array[key]:
                                chain_locate[key].append(sub_list_no_assign)
                        for sub_list_dup in tagged_list:
                            chain_locate[key].append(sub_list_dup)
                            left_vector, right_const = inequal_form(sub_list_dup, total_chain_num, bess_para)
                            left_matrix.append(left_vector)
                            right_matrix.append(right_const)
                            notated_final.extend(copy.deepcopy(sub_list_dup))
                        tagged_list = []
                        for sub_list in core_alloc_no_dup[key]:
                            chain_locate[key].append(sub_list)                            
                            left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
                            left_matrix.append(left_vector)
                            right_matrix.append(right_const)
                            notated_final.extend(copy.deepcopy(sub_list))
#                        print("core_tuple ", core_tuple)
#                            for module in sub_list_dup:
#                                print(module.nf_class, module.service_path_id, module.service_id, module.nf_type, module.core_num)
#                    print("chain locate", chain_locate.keys())
                    for nic_index in chain_locate:
#                        print("nic_index", nic_index, " length ", len(chain_locate[nic_index]))
                        return_vector = [0]*total_chain_num
                        for subgroup_of_nic in chain_locate[nic_index]:
                            get_vector, _ = inequal_form(subgroup_of_nic, total_chain_num, bess_para)
                            for chain_index in range(total_chain_num):
                                return_vector[chain_index] = return_vector[chain_index]+get_vector[chain_index]
                        left_matrix.append(return_vector)
                        right_matrix.append(int(nic["nic"][int(nic_index)]["throughput"])*1000000)
#                    print("left matrix", left_matrix)
#                    print("right matrix", right_matrix)
                    left_matrix = np.array(left_matrix)
                    right_matrix = np.array(right_matrix)
                    t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
#                    print "Throughput", t
                    mr =  marginalRate(chain_rate, t)
#                    print "MarginalRate", mr
                    notated_final.extend( copy.deepcopy(p4_list))
                    notated_final.sort(key=lambda l: (l.service_path_id, l.service_id))
#                    print("length of notated_final",len(notated_final))
                    tmp_module_list = tag_from_notated_list(tmp_module_list, notated_final)
                    chain_list, cut_index = segment_module_list(tmp_module_list)
                    start = -1
                    pattern_len = len(notated_final)
                    total_throughput = 0
                    chain_throughput = {}
                    #print "MarginalRate", marginalRate(chain_rate, t)
                    fail_satisfaction = False
                    for chain_index in range(total_chain_num):
                        if not_satisfy_rate(t[chain_index], chain_rate[chain_index], False):
                            fail_satisfaction = True
#                            print("found case chain "+str(chain_index))
#                            print(chain_throughput[chain_index])
#                            print(beta_para[chain_index]*chain_throughput[chain_index])
                    total_throughput = sum(mr)
                    core_num_all = []
                    for module in notated_final:
                        core_num_all.append([module.nic_index, module.core_num])                        
                    if not fail_satisfaction:
                        pattern_throughput_dict.append([pattern, core_num_all, mr, total_throughput])                        
                        success_count +=1
#                        print [pattern, core_num_all, mr, total_throughput]
        print "success count", success_count
    return pattern_throughput_dict

def write_out_pattern_file(all_pattern_dict, chosen_pattern):
    '''
    Output format: pattern adopt_bit executed_bit core_optimization_tuple total_throughput
    '''
    find_bool = False
    pattern_fp = open('pattern.txt', 'w')
    for item in all_pattern_dict:
        recorded_data = []
        recorded_data.append(item[0])
        if item[0] == chosen_pattern:
            if not find_bool:
                recorded_data.append(1)
                recorded_data.append(1)
                find_bool = True
            else:
                recorded_data.append(0)
                recorded_data.append(0)
            
        else:
            recorded_data.append(0)
            recorded_data.append(0)
        recorded_data = recorded_data + item[1:]

        for item in recorded_data:
            pattern_fp.write(str(item))
            pattern_fp.write('\t')
        pattern_fp.write('\n')

    pattern_fp.close()
    return

def optimize_pick(all_pattern_dict):
    '''
    This func sortss <pattern, throughput> dictionary
    '''
#    print(all_pattern_dict)
    all_pattern_dict_order = sorted(all_pattern_dict, key=itemgetter(-1), reverse=True)
#    print('chosen result: ')
#    print(all_pattern_dict_order[0])
    chosen_pattern = all_pattern_dict_order[0][0]
    module_info = all_pattern_dict_order[0][1]
    expected_throughput = all_pattern_dict_order[0][-1]
    write_out_pattern_file(all_pattern_dict_order, chosen_pattern)

    return chosen_pattern, module_info, expected_throughput

def apply_pattern(module_list, chosen_pattern, module_info, bess_para):
    '''
    This func would apply chosen placement option 'chosen_pattern' to
    all modules 'module_list' and mark the duplication information on 
    each module (i.e. how many cores for each module)
    '''
    if chosen_pattern <0:
        print("no available assignment")
        return
    total_len = len(module_list)
    print(chosen_pattern)
    print(module_info)
    for i in range(len(module_list)):
        mod_bit = (chosen_pattern>>(total_len-i-1))%2
        module_list[i].nf_type = mod_bit
        module_list[i].core_num = int(module_info[i][1])
        module_list[i].nic_index = int(module_info[i][0])
#    for module in module_list:
#        print(module.nf_class, module.nf_type, module.core_num)
    '''
    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    tmp_module_list = copy.deepcopy(module_list)
    bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
    for index in range(len(bess_subgroup_list)):
        subgroup = bess_subgroup_list[index]
        bess_subgroup_list[index] = tag_core_index(subgroup)
    left_matrix = []
    right_matrix = []
    for sub_list in bess_subgroup_list:
        left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
        left_matrix.append(left_vector)
        right_matrix.append(right_const)
    sum_of_left_traffic = [0]*total_chain_num
    sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
    left_matrix.append(sum_of_left_traffic)
    right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
    left_matrix = np.array(left_matrix)
    right_matrix = np.array(right_matrix)
    print "left matrix", left_matrix
    print "right matrix", right_matrix
    t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
    mr =  marginalRate(chain_rate, t)
    '''
    return  module_list

def log_module(module_list):
    '''
    This func is a debug function to check status of each module. It has no
    return value.
    '''
    PLACE_LOGGER.info("Log module starts")
    for module in module_list:
#        print("module %s, nf_type %d" % (module.nf_class, module.nf_type))
#        print("module %s, spi: %d, si: %d, nf_type %d, core_num: %s, nic_index: %d, bounce: %r, merge: %r, core_index: %d", \
#            module.nf_class, module.service_path_id, module.service_id, module.nf_type, module.core_num, module.nic_index,  module.bounce, module.merge, module.core_index)
        PLACE_LOGGER.debug("module %s, spi: %d, si: %d, nf_type %d, core_num: %s, nic_index: %d, bounce: %r, merge: %r, core_index: %d", \
            module.nf_class, module.service_path_id, module.service_id, module.nf_type, module.core_num, module.nic_index,  module.bounce, module.merge, module.core_index)
    PLACE_LOGGER.info("Log module ends")
    return

def next_optimize_pick():
    '''
    This func is used to read in FILE pattern.txt and pick the next best pattern.
    Without exception, this func is called when P4 compiler finds placement cannot
    be accepted, so NFCP goes on to the next best placement option.
    '''
    assert os.path.isfile('./pattern.txt')
    pattern_fp = open('./pattern.txt', 'r')
    choose = False
    past_pattern = -1
    chosen_pattern = 0
    change = False
    writeout_list = []
    core_alloc = None
    for line in pattern_fp:
        line_copy = line
        information = line.split("\t")
        assert len(information)>3
        if not choose:
            if int(information[1]) == 1:
                past_pattern = int(information[0])
                information[1] = 0
                change = True
            elif past_pattern == int(information[0]):
                information[2] = 1
            elif change and int(information[2])==0:
                chosen_pattern = int(information[0])
                core_alloc = information[3]
                information[1] = 1
                information[2] = 1
                choose = True
        else:
            if past_pattern == int(information[0]):
                information[2] = 1
        if '\n' in information:
            information.remove('\n')
        writeout_list.append(information)
    if not change:
        chosen_pattern = -1
    pattern_fp.close()
    writeout_fp = open('pattern.txt', 'w')
    for writeout_line in writeout_list:
        for item in writeout_line:            
            writeout_fp.write(str(item))
            writeout_fp.write('\t')
        writeout_fp.write('\n')
    writeout_fp.close()
    core_alloc = ast.literal_eval(core_alloc)
#    print core_alloc
    return chosen_pattern, core_alloc

def count_bounce(module_list, pattern):
    '''
    This func iterates all modules and check if the child module is the
    same type as itself. It they are different type, the child module 
    would mark bounce on itself. Then, this func would sum up the number
    of modules that are marked with bounce and return the value.
    '''
    count = 0
    ref = 0
    pattern_len = len(module_list)
    for module in module_list:
        module.nf_type = (pattern>>(pattern_len-ref-1))%2
    for module in module_list:
        if (module is module_list[0]) and module.is_bess():
            module.bounce = True
        else:
            for adj_node in module.adj_nodes:
                if adj_node.nf_type != module.nf_type:
                    adj_node.bounce = True
        ref += 1
    for module in module_list:
        if module.is_bess() and module.bounce:
            count += 1
    return count

def no_profile_optimize_pick(pattern_list, module_list, bess_para, constraints):  
    '''
    This func is assuming there is no profile information, so every BESS
    modules are assumed to use same number of cycles, and pick the best 
    throughput under this assumption.
    '''
    print "before", bess_para
    for item_index in bess_para:
        bess_para[item_index] = '20000'

    print bess_para

    all_chain_pattern_dict = speed_up_calc_cycle(pattern_list, module_list, bess_para, constraints)
    chosen_pattern, module_info, _ = optimize_pick(all_chain_pattern_dict)

        
#    all_pattern_dict_order = sorted(pattern_dict, key=itemgetter(1), reverse=True)
#    chosen_pattern = all_pattern_dict_order[0][0]
#    pattern_binary = "{0:b}".format(chosen_pattern)
#    tmp_tuple_list = [1]*pattern_binary.count('1')
#    chosen_tuple = tuple(tmp_tuple_list)
    return chosen_pattern, module_info

def individual_optimize_pick(module_list, bess_para, constraints):
    '''
    This func is implementing individual_pick algorithm. This func would
    maximize the throughput of each chain in order.
    '''
    nic = get_nic_info()
    module_list = tag_chain_index(copy.deepcopy(module_list))
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)
    chain_rate = get_rate()
    chosen_pattern = 0
    spare_core = int(nic["nic"][0]["core"])-RESERVE_CORE
    print "spare_core", spare_core

    for module in module_list:
        if module.nf_type == 2:
            module.nf_type = 0
        chosen_pattern = (chosen_pattern<<1) + module.nf_type
    
    cp_module_list = copy.deepcopy(module_list)
    chain_module_list, _ = segment_module_list(cp_module_list)
#    for module in cp_module_list:
#        print module.nf_class, module.nf_type
    num_of_chain = len(chain_module_list)
    final_module = []
    final_dict = {}
    usable_core = spare_core
    infeasible = False
    left_matrix = []
    right_matrix = []

    for chain_index in range(num_of_chain):
        chain_success = False
        chain_bess, chain_p4 = bfs_sort(copy.deepcopy(chain_module_list[chain_index]))
        for index in range(len(chain_bess)):
            subgroup = chain_bess[index]
            chain_bess[index] = tag_core_index(subgroup)
        print "chain_index", chain_index
        if len(chain_bess) == 0:
            final_module.extend(chain_p4)
            chain_success = True
        else:
            usable_core_left = usable_core - len(chain_bess)
            print "usable_core_left", usable_core , usable_core_left
            if usable_core < 0:
                infeasible = True
            else:
                dup_num, dup_list, no_dup_list = count_dup(0, range(len(chain_bess)), copy.deepcopy(chain_bess))
                for no_dup_sublist in no_dup_list:
                    left_vector, right_const = inequal_form(no_dup_sublist, len(chain_module_list), bess_para)
                    left_value = max(left_vector)
                    left_matrix.append(left_vector)
                    right_matrix.append(right_const)
                    if (right_const/float(left_value) < chain_rate[chain_index][0]):                        
                        infeasible = True
                    else:
                        usable_core -= 1

                for dup_sublist in dup_list:
                    left_vector, right_const = inequal_form(dup_sublist, len(chain_module_list), bess_para)
                    left_value = max(left_vector)
#                    for module in dup_sublist:
#                        print module.nf_class, module.nf_type
                    print "right_const/left_value", right_const/float(left_value), left_vector, right_const
                    find = False
                    if not_satisfy_rate(right_const/float(left_value), chain_rate[chain_index], True):
                        used_core = 2
                        while usable_core-used_core >=0 and find == False:
                            if not not_satisfy_rate(right_const*(used_core)/float(left_value), chain_rate[chain_index], True):
                                find = True
                                usable_core = usable_core - used_core
                                print "used_core", used_core

                            else:
                                used_core += 1
                        if find == False:
                            infeasible = True
                        else:
                            dup_sublist = tag_core([dup_sublist], tuple([used_core-1]))
                            chain_success = True
                    else:
                        find = True
                        usable_core = usable_core - 1
                        chain_success = True
                if dup_num == 0:
                    chain_success = True
                if chain_success:
                    for no_dup_sublist in no_dup_list:
                        final_module.extend(no_dup_sublist)
                    for dup_sublist in dup_list:
                        if dup_sublist[0].chain_index not in final_dict:
                            final_dict[dup_sublist[0].chain_index] = []   
                        final_dict[dup_sublist[0].chain_index].append(copy.deepcopy(dup_sublist))
                    final_module.extend(chain_p4)
    if not infeasible:
        print "inside infeasible"
        indexes = sorted(final_dict)
        for key in indexes:
            if usable_core >0:
                subgroup_bottleneck = []
                for subgroup in final_dict[key]:
                    subgroup_core = subgroup[0].core_num
                    print("tick, core %s" % subgroup_core)
                    _ , right_const = inequal_form(subgroup, len(chain_rate), bess_para)
                    subgroup_bottleneck.append(right_const/float(subgroup_core))
#                print("subgroup_bottleneck: %s" %subgroup_bottleneck)
                min_bottleneck = min(subgroup_bottleneck)
                min_index = subgroup_bottleneck.index(min_bottleneck)
#                print("min_index:%s, key:%s"%(min_index,key))
                stop = False
                more_core = 0
                bottleneck_core = final_dict[key][min_index][0].core_num
                target_left, target_right = inequal_form(final_dict[key][min_index], len(chain_rate), bess_para)
                target_left_value = max(target_left)
                while not stop and usable_core-more_core >=0:
#                    print("into add core")
                    more_core += 1
                    adjust_rate = (target_right/float(bottleneck_core))/target_left_value
#                    print("adjust:%s, chain_rate: %s"% (adjust_rate, chain_rate[key-1]))
                    if not_satisfy_rate(adjust_rate*(bottleneck_core+more_core), chain_rate[key-1], False):
                        stop = True
                tmp_list = tag_core([final_dict[key][min_index]], tuple([bottleneck_core-1+more_core-1]))
                final_dict[key][min_index] = tmp_list[0]
                usable_core = usable_core - (more_core-1)
            for sub_dup in final_dict[key]:
                final_module.extend(sub_dup)
        final_module.sort(key=lambda l: (l.service_path_id, l.service_id))
#        for module in final_module:
#            print module.nf_class, module.nf_type
        print "length of final_module",len(final_module)
        tmp_module_list = copy.deepcopy(module_list)
        tmp_module_list = tag_from_notated_list(tmp_module_list, final_module)
        bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
        left_matrix = []
        right_matrix = []
        for sub_list in bess_subgroup_list:
            left_vector, right_const = inequal_form(sub_list, len(chain_module_list), bess_para)
            left_matrix.append(left_vector)
            right_matrix.append(right_const)
        sum_of_left_traffic = [0]*len(chain_module_list)
        sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
        left_matrix.append(sum_of_left_traffic)
        right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
        print "left_matrix", left_matrix
        print "right_matrix", right_matrix
        left_matrix = np.array(left_matrix)
        right_matrix = np.array(right_matrix)
        t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
        mr =  marginalRate(chain_rate, t)
        print "Throughput", t
        print "Marginal rate", mr
        print "sum marginal rate", sum(mr)
        module_list = tag_from_notated_list(module_list, final_module)
    else:
        print "infeasible to match min_requirement"
    
    core_num_all = []
    for module in module_list:
        core_num_all.append([module.nic_index, module.core_num])
    print "core_num_all", core_num_all


    return chosen_pattern, core_num_all    

def all_p4_optimize_pick(pattern_list, module_list, bess_para):
    '''
    This func is implementing all_p4 algorithm. Whenever the module can
    choose placement, it would always choose P4.
    '''
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)

    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    chosen_pattern = 0
    print("length of module_list", len(module_list))
    for module in module_list:
        if module.nf_type == 2:
            module.nf_type = 0

    for i in range(len(module_list)):
        if i != (len(module_list)-1):
            chosen_pattern = ((chosen_pattern+int(module_list[i].nf_type))<<1)

    notated_list = copy.deepcopy(module_list)
    bess_subgroup_list, p4_list = bfs_sort(notated_list)
    for index in range(len(bess_subgroup_list)):
        subgroup = bess_subgroup_list[index]
        bess_subgroup_list[index] = tag_core_index(subgroup)
    dup_num, dup_list, no_dup_list = count_dup(0, range(len(bess_subgroup_list)), copy.deepcopy(bess_subgroup_list))
    chain_indexes = []
    for sub_list in dup_list:
        chain_indexes.append(sub_list[0].chain_index)
    unique_entries = set(chain_indexes)
    categorize_dict = {}
    for entry in unique_entries:
        categorize_dict[entry] = []
    nic = get_nic_info()
    spare_core_num = int(nic["nic"][0]["core"])-RESERVE_CORE-len(bess_subgroup_list)
    notated_final = []
    left_matrix = []
    right_matrix = []
    print "spare_core_num", spare_core_num , "len(unique_entries)", len(unique_entries)
    if len(unique_entries) != 0:
        each_chain_core = spare_core_num/len(unique_entries)
        for i in range(len(chain_indexes)):
            categorize_dict[chain_indexes[i]].append(dup_list[i])
        for chain_index in categorize_dict:
            subgroup_bottleneck = []
            for subgroup in categorize_dict[chain_index]:
                _ , right_const = inequal_form(subgroup, total_chain_num, bess_para)
                subgroup_bottleneck.append(right_const)
            min_bottleneck = min(subgroup_bottleneck)
            min_index = subgroup_bottleneck.index(min_bottleneck)
            dup_matrix = [0]*len(subgroup_bottleneck)
            dup_matrix[min_index] = each_chain_core
            dup_tuple = tuple(dup_matrix)
            categorize_dict[chain_index] = tag_core(categorize_dict[chain_index], dup_tuple)
            for subgroup in categorize_dict[chain_index]:
                notated_final.extend(subgroup)
                left_vector, right_const = inequal_form(subgroup, total_chain_num, bess_para)
                left_matrix.append(left_vector)
                right_matrix.append(right_const)
    for sub_list in no_dup_list:
        notated_final.extend(sub_list)
        left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
        left_matrix.append(left_vector)
        right_matrix.append(right_const)

    if len(left_matrix) != 0:
        sum_of_left_traffic = [0]*total_chain_num
        sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
        left_matrix.append(sum_of_left_traffic)
        right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
    
    print("left matrix", left_matrix)
    print("right matrix", right_matrix)
    left_matrix = np.array(left_matrix)
    right_matrix = np.array(right_matrix)
    t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
    mr = marginalRate(chain_rate, t)
    print "Marginal rate", mr
    print "Sum marginal rate", sum(mr)
    notated_final.extend(p4_list)
    notated_final.sort(key=lambda l: (l.service_path_id, l.service_id))
    module_list = tag_from_notated_list(module_list, notated_final)
    core_num_all = []
#    print("notated length", len(module_list))
    for module in module_list:
        core_num_all.append([module.nic_index, module.core_num])

    return chosen_pattern, core_num_all

def all_BESS_optimize_pick(pattern_list, module_list, bess_para, constraints):
    '''
    This func to deploy all modules in BESS. If there is any spare core, it 
    would do core optimization.
    '''
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)

    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    chosen_pattern = 0
    chosen_tuple = None
    
    for module in module_list:
        if module.nf_type == 2:
            module.nf_type = 1
    for i in range(len(module_list)):
        if i != (len(module_list)-1):
            chosen_pattern = ((chosen_pattern+int(module_list[i].nf_type))<<1)

    notated_list = copy.deepcopy(module_list)
    bess_subgroup_list, p4_list = bfs_sort(notated_list)
    for index in range(len(bess_subgroup_list)):
        subgroup = bess_subgroup_list[index]
        bess_subgroup_list[index] = tag_core_index(subgroup)
    dup_num, dup_list, no_dup_list = count_dup(0, range(len(bess_subgroup_list)), copy.deepcopy(bess_subgroup_list))
    chain_indexes = []
    for sub_list in dup_list:
        chain_indexes.append(sub_list[0].chain_index)
    unique_entries = set(chain_indexes)
    categorize_dict = {}
    for entry in unique_entries:
        categorize_dict[entry] = []
    nic = get_nic_info()
    spare_core_num = int(nic["nic"][0]["core"])-RESERVE_CORE-len(bess_subgroup_list)
    notated_final = []
    left_matrix = []
    right_matrix = []
    if len(unique_entries) != 0:
        each_chain_core = spare_core_num/len(unique_entries)
        for i in range(len(chain_indexes)):
            categorize_dict[chain_indexes[i]].append(dup_list[i])
        for chain_index in categorize_dict:
            subgroup_bottleneck = []
            for subgroup in categorize_dict[chain_index]:
                _ , right_const = inequal_form(subgroup, total_chain_num, bess_para)
                subgroup_bottleneck.append(right_const)
            min_bottleneck = min(subgroup_bottleneck)
            min_index = subgroup_bottleneck.index(min_bottleneck)
            dup_matrix = [0]*len(subgroup_bottleneck)
            dup_matrix[min_index] = each_chain_core
            dup_tuple = tuple(dup_matrix)
            categorize_dict[chain_index] = tag_core(categorize_dict[chain_index], dup_tuple)
            for subgroup in categorize_dict[chain_index]:
                notated_final.extend(subgroup)
                left_vector, right_const = inequal_form(subgroup, total_chain_num, bess_para)
                left_matrix.append(left_vector)
                right_matrix.append(right_const)
    for sub_list in no_dup_list:
        notated_final.extend(sub_list)
        left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
        left_matrix.append(left_vector)
        right_matrix.append(right_const)

    if len(left_matrix) != 0:
        sum_of_left_traffic = [0]*total_chain_num
        sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
        left_matrix.append(sum_of_left_traffic)
        right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)

    print("left matrix", left_matrix)
    print("right matrix", right_matrix)
    left_matrix = np.array(left_matrix)
    right_matrix = np.array(right_matrix)
    t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
    mr = marginalRate(chain_rate, t)
    print "Throughput", t
    print "MarginalRate", mr
    print "sum Marginal rate", sum(mr)

    notated_final.extend(p4_list)
    notated_final.sort(key=lambda l: (l.service_path_id, l.service_id))
    module_list = tag_from_notated_list(module_list, notated_final)
    core_num_all = []
    print("notated length", len(module_list))
    for module in module_list:
        core_num_all.append([module.nic_index, module.core_num])

    return chosen_pattern, core_num_all


def no_core_alloc_optimization_pick(pattern_list, module_list, bess_para): 
    '''
    This func implements no core_optimization algorithm. It only considers
    pattern effect (i.e. no packing phase) to pick optimal throughput.
    '''
    chosen_pattern = None
    chosen_tuple = tuple([])
    all_pattern_dict = no_core_op_calc_cycle(pattern_list, module_list, bess_para)
    all_pattern_dict_order = sorted(all_pattern_dict, key=itemgetter(1), reverse=True)
    chosen_pattern = all_pattern_dict_order[0][0]
    pattern_binary = "{0:b}".format(chosen_pattern)
    tmp_tuple_list = [1]*pattern_binary.count('1')
    chosen_tuple = tuple(tmp_tuple_list)
    return chosen_pattern, chosen_tuple

def E2_optimization_pick(pattern_list, module_list, bess_para):
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)
    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    pattern_dict = []
#    counter=0

    for pattern in pattern_list:
#        pattern_binary = "{0:b}".format(pattern)
        
#        tmp_tuple_list = [1]*pattern_binary.count('1')
#        ones_tuple = tuple(tmp_tuple_list)
        notated_list = copy.deepcopy(module_list)
        total_module_num = len(module_list)
#        notated_list = notate_list(notated_list, ones_tuple, pattern)
        for module_index in range(total_module_num):
            mode_bit = (pattern>>(total_module_num - module_index-1))%2
            notated_list[module_index].nf_type = mode_bit


        bess_subgroup_list, p4_list = bfs_sort(notated_list)
        '''
        if pattern == 243740:
            print "pattern_binary", pattern
            print "length of bess_subgroup", len(bess_subgroup_list)
            for subgroup in bess_subgroup_list:
                print "subgroup"
                for module in subgroup:
                    print module.nf_class, module.nf_type
        '''
            
         
        for index in range(len(bess_subgroup_list)):
            subgroup = bess_subgroup_list[index]
            bess_subgroup_list[index] = tag_core_index(subgroup)
        dup_num, dup_list, no_dup_list = count_dup(0, range(len(bess_subgroup_list)), copy.deepcopy(bess_subgroup_list))
        subgroup_count = len(no_dup_list)+len(dup_list)
        chain_indexes = []
        for sub_list in dup_list:       
            chain_indexes.append(sub_list[0].chain_index)
        unique_entries = set(chain_indexes)
        categorize_dict = {}
        for entry in unique_entries:
            categorize_dict[entry] = []
        nic = get_nic_info()
        spare_core_num = int(nic["nic"][0]["core"])-RESERVE_CORE-len(bess_subgroup_list)
        notated_final = []
        left_matrix = []
        right_matrix = []
        if len(unique_entries) != 0 and spare_core_num>0:
            each_chain_core = spare_core_num/len(unique_entries)
            for i in range(len(chain_indexes)):
                categorize_dict[chain_indexes[i]].append(dup_list[i])
            for chain_index in categorize_dict:
                subgroup_bottleneck = []
                for subgroup in categorize_dict[chain_index]:
                    left_vector , right_const = inequal_form(subgroup, total_chain_num, bess_para)
                    left_value = float(max(left_vector))
                    subgroup_bottleneck.append(right_const/float(left_value))
                min_bottleneck = min(subgroup_bottleneck)
                min_index = subgroup_bottleneck.index(min_bottleneck)
                dup_matrix = [0]*len(subgroup_bottleneck)
                dup_matrix[min_index] = each_chain_core
                dup_tuple = tuple(dup_matrix)
#                print each_chain_core, dup_tuple
                categorize_dict[chain_index] = tag_core(categorize_dict[chain_index], dup_tuple)
                for subgroup in categorize_dict[chain_index]:
                    notated_final.extend(subgroup)
                    left_vector, right_const = inequal_form(subgroup, total_chain_num, bess_para)
                    left_matrix.append(left_vector)
                    right_matrix.append(right_const)
        for sub_list in no_dup_list:
            notated_final.extend(sub_list)
            left_vector, right_const = inequal_form(sub_list, total_chain_num, bess_para)
            left_matrix.append(left_vector)
            right_matrix.append(right_const)
        
        if len(left_matrix) != 0:
            sum_of_left_traffic = [0]*total_chain_num
            sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
            left_matrix.append(sum_of_left_traffic)
            right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
        
        left_matrix = np.array(left_matrix)
        right_matrix = np.array(right_matrix)
        t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
        mr = marginalRate(chain_rate, t)
        notated_final.extend(p4_list)
        notated_final.sort(key=lambda l: (l.service_path_id, l.service_id))
        core_num_all = []
#        print pattern
        for module in notated_final:
            if module.nf_type == 0:
                assert module.nic_index == -1
            else:
                assert module.nic_index == 0
            core_num_all.append([module.nic_index, module.core_num])
        pattern_dict.append([pattern, core_num_all, mr, -subgroup_count])
#        print("length of subgroup list", len(bess_subgroup_list))

    all_pattern_dict_order = sorted(pattern_dict, key=itemgetter(-1, -2), reverse=True)   
    print "bounce_num:" , all_pattern_dict_order[0][-1]
    chosen_pattern = all_pattern_dict_order[0][0]
    module_info  = all_pattern_dict_order[0][1]
#    print "all_pattern_dict_order", all_pattern_dict_order[0]
    print ("Marginal rate: ", all_pattern_dict_order[0][-2])
    print "sum Marginal", sum(all_pattern_dict_order[0][-2])
    print "module_info", module_info
    print "chosen_pattern", chosen_pattern

    return chosen_pattern, module_info

def heuristic_core_allocation(module_list):
    
    pattern_list = enum_case(module_list)
#    print(pattern_list)
    bess_dict_para, constraints = read_para()

    all_chain_pattern_dict = speed_up_calc_cycle(pattern_list, module_list, bess_dict_para, constraints)
    
    return all_chain_pattern_dict, bess_dict_para
    
    

'''
    nic = get_nic_info()
    avail_nic_num = len(nic["nic"])
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)

    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    spare_core = int(nic["nic"][0]["core"])-RESERVE_CORE
    usable_core = spare_core

    notate_module_list = copy.deepcopy(module_list)
    chain_module_list, _ = segment_module_list(notate_module_list)
    total_chain_num = len(chain_module_list)

    final_module = []
    infeasible = False

    for chain_index in range(total_chain_num):
        chain_bess, chain_p4 = bfs_sort(copy.deepcopy(chain_module_list[chain_index]))
        if len(chain_bess) == 0:
            final_module.extend(chain_p4)
            chain_success = True
        else:
            for i in range(len(chain_bess)):
                subgroup = chain_bess[i]
                chain_bess[i] = tag_core_index(subgroup)
            dup_num, dup_list, no_dup_list = count_dup(0, range(len(chain_bess)), chain_bess)
            bool_tag = []
            for no_dup_sublist in no_dup_list:
                left_vector, right_const = inequal_form(no_dup_sublist, len(chain_module_list), bess_para)
                left_value = max(left_vector)
                if (right_const/float(left_value) < chain_rate[chain_index][0]):  
                    infeasible = True
                else:
                    usable_core -= 1
            for dup_sublist in dup_list:
                left_vector, right_const = inequal_form(dup_sublist, len(chain_module_list), bess_para)
                left_value = max(left_vector)
                if not_satisfy_rate(right_const/float(left_value), chain_rate[chain_index], True):
                    used_core = math.ceil(chain_rate[chain_index][0]*float(left_value)/right_const)
'''


def mode_select_pattern_list(mode, module_list):
    pattern_list = []
    if mode == 3:
        node_total = len(module_list)
        p4_pattern = (1<<node_total)-1
        pattern_list.append(p4_pattern)
    elif mode == 7:
        pattern_list = pattern_list
    else:
        pattern_list = enum_case(module_list)
        
    return pattern_list

def mode_select_decision_pattern(mode, chain_enum_list, all_modules, bess_dict_para, constraints):
    chosen_pattern = -1
    core_alloc = None
    if mode == 0 or mode == 6:
#        all_chain_pattern_dict = calc_cycle(chain_enum_list, all_modules, bess_dict_para, constraints)
        all_chain_pattern_dict = speed_up_calc_cycle(chain_enum_list, all_modules, bess_dict_para, constraints)
        chosen_pattern, core_alloc, _ = optimize_pick(all_chain_pattern_dict)
    elif mode == 1:
        chosen_pattern, core_alloc = no_profile_optimize_pick(chain_enum_list, all_modules, bess_dict_para, constraints)
    elif mode == 2:
        chosen_pattern, core_alloc = individual_optimize_pick( all_modules, bess_dict_para, constraints)
    elif mode == 3:
        chosen_pattern, core_alloc = all_p4_optimize_pick(chain_enum_list, all_modules, bess_dict_para)
    elif mode == 4:
        all_chain_pattern_dict = no_core_op_calc_cycle(chain_enum_list, all_modules, bess_dict_para)
        chosen_pattern, core_alloc = optimize_pick(all_chain_pattern_dict)
    elif mode == 5:
        chosen_pattern, core_alloc = E2_optimization_pick(chain_enum_list, all_modules, bess_dict_para)
    elif mode == 7:
        chosen_pattern, core_alloc = all_BESS_optimize_pick(chain_enum_list, all_modules, bess_dict_para, constraints)
        
    return chosen_pattern, core_alloc

def place_decision(nfcp_parser, enumerate_bool, op_mode):
    bess_dict_para = {}
    constraints = {}
    decision_pattern = None
    all_modules = []
    chain_enum_list = None
    modules = []
    """
    for flowspec_name, nfchain_name in nfcp_parser.scanner.flowspec_nfchain_mapping.items():
        chain_ll_node = nfcp_parser.scanner.struct_nlinkedlist_dict[nfchain_name]
        nf_graph_chain = convert_nf_graph(chain_ll_node)
        chain_modules = nf_graph_chain.list_modules()
        modules.extend(chain_modules)
        print "length of each chain", len(chain_modules)
    """
    
    nf_graph = convert_global_nf_graph(nfcp_parser.scanner)
    modules = nf_graph.list_modules()
    modules.sort(key=lambda l: (l.service_path_id, l.service_id))
#    for module in modules:
#        print ("module %s, spi: %d, si: %d, nf_type %d, core_num: %s, nic_index: %d, bounce: %r, merge: %r, core_index: %d", \
#            module.nf_class, module.service_path_id, module.service_id, module.nf_type, module.core_num, module.nic_index,  module.bounce, module.merge, module.core_index)

    if not enumerate_bool:
        bess_dict_para, constraints = read_para()
        chain_enum_list = mode_select_pattern_list(op_mode, modules)
        decision_pattern, core_alloc = mode_select_decision_pattern(op_mode, chain_enum_list, modules, bess_dict_para, constraints)
    else:
        decision_pattern, core_alloc = next_optimize_pick()
    all_modules = apply_pattern(modules, decision_pattern, core_alloc, bess_dict_para)
    if all_modules:
        log_module(all_modules)
    else:
        warnings.warn("no available placement")
    return all_modules

if __name__ == "__main__":
    place_decision()
