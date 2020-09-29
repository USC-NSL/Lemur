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
import sys
import numpy as np
from ast import literal_eval as make_tuple
from user_level_parser.UDLemurUserListener \
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
    """ Read data from module_data.txt and construct
        a dictionary of BESS module name to profiled
        cycles and extract the core constraints

    Parameter:
    
    Returns:
    bess_para: a dictionary of BESS module name 
                mapping to its profiled cycles
    constraints_all: number of available BESS cores

    """
    bess_para = {}
    constraints_all = {}

    try:
        fp = open('module_data.txt', 'r')
    except:
        print("module_data.txt is not provided. Fatal error!")
        sys.exit()

    for line in fp:
        information = line.split()
        if information:
            assert len(information) == 3
            if information[0].lower() == 'bess':
                bess_para[information[1]] = information[2]
            else:
                warnings.warn('Warning: unrecognized device info or using p4 module')

    constraint = bess_para.get("constraints")
    if constraint:
        constraints_all['bess_core'] = int(constraint)
    return bess_para, constraints_all

def enum_case(module_list):
    """ Enum all possible placement for NF chain.
    
    Parameter:
    module_list: all NF modules

    Returns:
    enum_list: a list of all possible placement
    """

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

def notate_list(target_list, bess_core, mask_pattern):
    """ Notate deployment hardware and assigned # of cores
        to each NF instance in NF chains

    Parameter:
    target_list: all NF modules
    bess_core: a list of # cores to be assigned to each
               NF instance
    mask_pattern: the deployment decision

    Returns:
    target_list: all notated NF modules

    """
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
    """ Segment all NF modules into lists of modules

    Parameter:
    all_modules: all NF modules

    Returns:
    chain_module_list: lists of (service chain) modules
    cut_index: the indexes of all NF modules that are
               used to separate service chains
    """
    start = 0
    chain_module_list = []
    cut_index = []
    for module in all_modules:
        if len(module.adj_nodes)==0:
            cut_index.append(all_modules.index(module))
    for index in cut_index:
        module_list = all_modules[start: index+1]
        start = index+1
        chain_module_list.append(module_list)
    return chain_module_list, cut_index

def no_core_op_calc_cycle(pattern_list, module_list, bess_para):
    """ Calculate the throughput of no_core_optimization algorithm

    Parameter:
    pattern_list: all possible placements
    module_list: all NF modules
    bess_para: BESS module name mapping to profiled cycles

    Returns:
    pattern_throughput_dict: a dictionary of placement and its
                             corresponding throughput
    """
    nic = get_nic_info()
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
            module_list_backup = copy.deepcopy(module_list)
            total_module_num = len(module_list)
            for module_index in range(total_module_num):
                mode_bit = (pattern>>(total_module_num - module_index-1))%2
                module_list_backup[module_index].nf_type = mode_bit
                if mode_bit == 1:
                    module_list_backup[module_index].nic_index = 0
            notate_module_list = module_list_backup
            cp_final_module = copy.deepcopy(notate_module_list)

            bess_subgroup_list, p4_list = bfs_sort(notate_module_list)
            left_matrix = []
            right_matrix = []
            for sub_list in bess_subgroup_list:
                left_vector, right_const = inequal_form(sub_list, \
                                        total_chain_num, bess_para)
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

    return pattern_throughput_dict

def not_satisfy_rate(test, restrict, min_only_bool):
    """ Examine if the computed throughput meets SLO

    Parameter:
    test: examined throughput number
    restrict: min and max throughput in a list
    min_only_bool: flagged when examining only min
                   throughput

    Returns:
    True if the throughput meets SLO requirement
    False otherwise

    """

    if min_only_bool:
        return test<int(restrict[0])
    else:
        if test<int(restrict[0]) or test>int(restrict[1]):
            return True
        else:
            return False

def get_rate():
    """ Read min/max requirement from chain_rate.txt

    Parameter:

    Returns:
    rate: min and max throughput in a list

    """
    rate = []
    fp = open("chain_rate.txt",'r')
    for line in fp:
        content = line.split()
        new_list = []
        for number in content:
            new_list.append(float(number))
        rate.append(tuple(new_list))
    rate = tuple(rate)
    return rate

def get_nic_info():
    """ Load available nic(s) info

    Parameter:

    Returnes:
    data: a dictionary containing each nic detail
    """
    with open('device.txt') as f:
        data = json.load(f)
    return data

def get_delay():
    """ Get delay requirement from max_delay.txt

    Parameter:

    Returns:
    delay_ls: a list of max delay for each chain
    
    """
    fp = open("max_delay.txt", 'r')
    delay_ls = []
    for line in fp:
        delay_ls.append(float(line)*FREQ)
    return delay_ls

def bfs_sort(module_list):
    """ Find out subgroups in chains

    Parameter:
    module_list: all NF modules of a service chain

    Returns:
    bess_list: lists of BESS subgroups
    p4_list: NF instances assigned to PISA switch

    """

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
    """ Differentiate non-replicable/replicable subgroups

    Parameter:
    nic_index: the subgroup is assigned to which nic index
    list_index: index of the number of subgroups
    bess_subgroup_list: lists of subgroup

    Returns:
    dup_num: number of replicable subgroups
    dup_list: a list of replicable subgroups
    no_dup_list: a list of non-replicable subgroups

    """

    dup_num = len(list_index)
    dup_list = []
    no_dup_list = []
    for index in list_index:
        dup_bool = True
        sub_list = bess_subgroup_list[index]
        for module in sub_list:
            module.nic_index = nic_index
        for module in sub_list:
            if module.is_dup_avoid() or module.is_branch_node()\
                                    or len(module.prev_nodes)>1:
                dup_num -= 1
                dup_bool = False
                break
        if dup_bool:
            dup_list.append(copy.deepcopy(sub_list))
        else:
            no_dup_list.append(copy.deepcopy(sub_list))
    return dup_num, dup_list, no_dup_list

def tag_core(dup_list, dup_tuple):
    """ Notate number of cores assigned to 
        replicable subgroups

    Parameter:
    dup_list: a list of replicable subgroups
    dup_tuple: a tuple where each element represents
               number of cores assigned to a subgroup

    Returns:
    dup_list: a notated list of replicable subgroups

    """

    for i in range(len(dup_list)):
        for module in dup_list[i]:
            module.core_num = 1+dup_tuple[i]
            if module.core_num <1:
                print "Core assignment error"
                sys.exit()
    return dup_list

def tag_chain_index(module_list):
    """ Notate chain index to each module

    Parameter:
    module_list: all NF modules

    Returns:
    module_list: all NF modules with chain index notated    

    """
    index_ptr = 1
    for module in module_list:
        module.chain_index = index_ptr
        if len(module.adj_nodes)==0:
            index_ptr+=1
    return module_list

def tag_core_index(subgroup):
    """ Tag CPU core index to each module
        in a subgroup 
    
    Parameter:
    subgroup: a subgroup of modules

    Returns:
    return_subgroup: the subgroup of modules with core
                     index notated

    """
    default_value = 0
    queue_a = []
    return_subgroup = []
    cp_subgroup = copy.deepcopy(subgroup)

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
    return return_subgroup

def tag_weight(module_list, weight_dict):
    """ Tag adjusted weight for throughput computation

    Parameter:
    module_list: all NF modules
    weight_dict: a dictionary of weights to be tagged

    Returns:
    module_list: all NF modules with tagged adjusted weight

    """

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
            index_str = "W%d%d%d%d" % (module_list[i].service_path_id,\
                        module_list[i].service_id,\
                        adj_node.service_path_id,\
                        adj_node.service_id)
            adj_node.weight = adj_node.weight + \
                        module_list[i].weight*weight_dict[index_str]
    return module_list

def tag_from_notated_list(module_list, notated_list):
    """ Copy essential notations from another list

    Paramter:
    module_list: a list of NF modules to be notated
    notated_list: the list that already contains 
                  notation information

    """
    for i in range(len(module_list)):
        module_list[i].core_num = notated_list[i].core_num
        module_list[i].nic_index = notated_list[i].nic_index
        module_list[i].chain_index = notated_list[i].chain_index
        module_list[i].nf_type = notated_list[i].nf_type
        module_list[i].core_index = notated_list[i].core_index

    return module_list

def generate_weight(module_list):
    """ Calculate the adjusted weight for throughput
        computation and store them in a dictionary

    Parameter:
    module_list: all NF modules

    Returns:
    weight_dict: a dictionary containing adjusted
                 weight information
 
    """
    weight_dict={}
    module_list.sort(key=lambda l: (l.service_path_id, l.service_id))
    for i in range(len(module_list)):
        for adj_node in module_list[i].adj_nodes:
            transition_str = "W%d%d%d%d" % (module_list[i].service_path_id,\
                            module_list[i].service_id,\
                            adj_node.service_path_id, \
                            adj_node.service_id)
            weight_dict[transition_str] = \
                            int(1)/float(len(module_list[i].adj_nodes))
    return weight_dict

def err_add(number, percentage):
    """ Add artificial error in percentage 
        to the profiled CPU cycle

    Parameter:
    number: the profiled CPU cycle
    percentage: error percentage

    Returns:
    adjusted CPU cycles
    """

    return number*(1+percentage)

def inequal_form(sub_list, total_chain_num, para_list):
    """ Calculate incoming traffic and outgoing traffic
        for each subgroup to formulate inequality equation

    Parameter:
    sub_list: a list of subgroup modules
    total_chain_num: number of service chains
    para_list: a dictionary of BESS module name and its
               profiled CPU cycles

    Returns:
    return_vector: a vector of weight that will multiply
                   to a vector of chain throughput variable
    return_weight: throughput constraint

    """

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
            sys.exit()
        str_list.append("%d%d" % (module.service_path_id, module.service_id))
        if module.core_index not in right_index_dict:
            right_index_dict[module.core_index] = 0
        right_index_dict[module.core_index] += \
            module.weight*err_add(int(para_list.get(str(module.nf_class))),\
            error_rate)/float(core_num)

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

    return return_vector, return_weight

def calc_delay(module_list, para_list):
    """ Compute the largest delay observed till
        the module itself for all modules

    Parameter:
    module_list: all NF modules
    para_list: a dictionary of BESS modules and
               its profiled CPU cycles

    Returns:
    module_list: all NF modules with max-observed
                 delay notated
    """
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
    """ Verify if each chain meets delay requirement
    
    Parameter:
    module_list: all NF modules

    Returns:
    success_bool: flagged if delay requirement is met
    end_of_node_time: a list of calculated delays for
                      all chains
    """
    end_of_node_time = []
    for module in module_list:
        if len(module.adj_nodes) == 0:
            end_of_node_time.append(module.time)
    delay_ls = get_delay()
    success_bool = True
    for index in range(len(delay_ls)):
        if delay_ls[index] < end_of_node_time[index]:
            success_bool = False
    return success_bool, end_of_node_time
    

def speed_up_calc_cycle(pattern_list, module_list, bess_para, constraints):
    """ Calculate estimated throughput for all possible placement

    Parameter:
    pattern_list: all possible placement
    module_list: all NF modules
    bess_para: a dictionary of BESS modules and its profiled CPU cycles
    constraints: number of available CPU cores

    Returns:
    pattern_throughput_dict: a list of possible placements with 
                             their estimated throughput
    """

    nic = get_nic_info()
    avail_nic_num = len(nic["nic"])
    pattern_throughput_dict = []
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)

    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    spare_core = int(nic["nic"][0]["core"])-RESERVE_CORE
    pattern_counter = 0
    for pattern in pattern_list:
        pattern_counter += 1
        usable_core = spare_core
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
            notate_module_list = notate_list(module_list_backup,\
                                             ones_tuple, pattern)
            notate_module_list = calc_delay(notate_module_list, bess_para)
            time_bool, end_of_node_time = verify_time(notate_module_list)

            if not time_bool:
                continue

            chain_module_list, _ = segment_module_list(notate_module_list)
            infeasible = False
            final_module = []
            final_dict = []

            for chain_index in range(total_chain_num):
                chain_success = False
                chain_bess, chain_p4 = bfs_sort(copy.deepcopy(\
                                            chain_module_list[chain_index]))
                if len(chain_bess) == 0:
                    final_module.extend(chain_p4)
                    chain_success = True
                else:
                    for i in range(len(chain_bess)):
                        subgroup = chain_bess[i]
                        chain_bess[i] = tag_core_index(subgroup)
                    dup_num, dup_list, no_dup_list = count_dup(0,\
                                         range(len(chain_bess)), chain_bess)
                    bool_tag = []
                    for no_dup_sublist in no_dup_list:
                        left_vector, right_const = inequal_form(no_dup_sublist,\
                                         len(chain_module_list), bess_para)
                        left_value = max(left_vector)
                        if (right_const/float(left_value) < chain_rate[chain_index][0]): 
                            infeasible = True
                        else:
                            usable_core -= 1

                    for dup_sublist in dup_list:
                        left_vector, right_const = inequal_form(dup_sublist,\
                                           len(chain_module_list), bess_para)
                        left_value = max(left_vector)
                        if not_satisfy_rate(right_const/float(left_value),\
                                             chain_rate[chain_index], True):
                            used_core = math.ceil(chain_rate[chain_index][0]*\
                                               float(left_value)/right_const)
                            if used_core > usable_core:
                                infeasible = True
                            else:
                                usable_core = usable_core - used_core
                                dup_sublist = tag_core([dup_sublist],\
                                                        tuple([used_core-1]))
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
                                final_dict.append(dup_list[index])
                            else:
                                final_module.extend(dup_list[index])
                        final_module.extend(chain_p4)
            pattern_preallocate_end = time.time()
            if not infeasible:
                if len(final_dict)>0 and usable_core>0:

                    core_iter = itertools.combinations_with_replacement(\
                                list(range(len(final_dict))), int(usable_core))
                    core_dict = []
                    for core_tuple in core_iter:
                        tmp_ls = []
                        for index in range(len(final_dict)):
                            tmp_ls.append(core_tuple.count(index))
                        core_tuple = tuple(tmp_ls)
                        cp_final_dict = copy.deepcopy(final_dict)
                        if core_tuple in core_dict:
                            continue
                        else:
                            core_dict.append(core_tuple)
                        if sum(core_tuple) == usable_core:
                            cp_final_module = copy.deepcopy(final_module)
                            cp_final_module.sort(key=lambda l: (\
                                        l.service_path_id, l.service_id))
                            core_tuple = list(core_tuple)
                            for i in range(len(cp_final_dict)):
                                bottleneck_core = cp_final_dict[i][0].core_num
                                core_tuple[i]= core_tuple[i]+bottleneck_core-1
                            tagged_list = tag_core(cp_final_dict, \
                                                        tuple(core_tuple))
                            for sublist in tagged_list:
                                cp_final_module.extend(sublist)
                            cp_final_module.sort(key=lambda l: (\
                                        l.service_path_id, l.service_id))
                            tmp_module_list = copy.deepcopy(module_list)
                            tmp_module_list = tag_from_notated_list(\
                                            tmp_module_list, cp_final_module)
                            bess_subgroup_list, p4_list = \
                                            bfs_sort(tmp_module_list)
                            left_matrix = []
                            right_matrix = []
                            for sub_list in bess_subgroup_list:
                                left_vector, right_const = \
                                            inequal_form(sub_list, \
                                                         total_chain_num, \
                                                         bess_para)
                                left_matrix.append(left_vector)
                                right_matrix.append(right_const)
                            sum_of_left_traffic = [0]*total_chain_num
                            sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
                            left_matrix.append(sum_of_left_traffic)
                            right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
                            left_matrix = np.array(left_matrix)
                            right_matrix = np.array(right_matrix)
                            t = maximizeMarginalRate(chain_rate, \
                                                     left_matrix, \
                                                     right_matrix)
                            mr =  marginalRate(chain_rate, t)
                            no_record = False
                            if sum(list(t)) == 0:
                                no_record = True
                            if not no_record:
                                core_num_all = []
                                for module in cp_final_module:
                                    core_num_all.append([module.nic_index, \
                                                         module.core_num])
                                pattern_throughput_dict.append([pattern, \
                                                                core_num_all, \
                                                                end_of_node_time, \
                                                                sum(end_of_node_time), \
                                                                mr, 
                                                                sum(mr)])
                            core_end = time.time()
                elif len(final_dict)>0 and usable_core == 0:
                    cp_final_module = copy.deepcopy(final_module)
                    for sublist in final_dict:
                        cp_final_module.extend(sublist)
                    cp_final_module.sort(key=lambda l: (l.service_path_id, \
                                                        l.service_id))
                    tmp_module_list = copy.deepcopy(module_list)
                    tmp_module_list = tag_from_notated_list(tmp_module_list, \
                                                            cp_final_module)
                    bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
                    left_matrix = []
                    right_matrix = []
                    for sub_list in bess_subgroup_list:
                        left_vector, right_const = inequal_form(sub_list, \
                                                                total_chain_num, \
                                                                bess_para)
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
                        pattern_throughput_dict.append([pattern, core_num_all, \
                                                        mr, sum(mr)])
                elif len(final_dict) == 0:
                    cp_final_module = copy.deepcopy(final_module)
                    cp_final_module.sort(key=lambda l: (l.service_path_id, \
                                                        l.service_id))
                    tmp_module_list = copy.deepcopy(module_list)
                    tmp_module_list = tag_from_notated_list(tmp_module_list, \
                                                            cp_final_module)
                    bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
                    left_matrix = []
                    right_matrix = []
                    for sub_list in bess_subgroup_list:
                        left_vector, right_const = inequal_form(sub_list, \
                                                                total_chain_num, \
                                                                bess_para)
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
                        pattern_throughput_dict.append([pattern, core_num_all, \
                                                        end_of_node_time, \
                                                        sum(end_of_node_time), \
                                                        mr, sum(mr)])
    return pattern_throughput_dict

def write_out_pattern_file(all_pattern_dict, chosen_pattern):
    """ Write all possible placement and their estimated throughput
        to a file 'pattern.txt'

    Parameter:
    all_pattern_dict: all possible placement and their estimated throughput
    chosen_pattern: the chosen placement to be deployed at current moment

    Output format: 
    pattern adopt_bit executed_bit core_optimization_tuple total_throughput
    """
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
    """Sorts <pattern, throughput> dictionary

    Parameter:
    all_pattern_dict: <pattern, throughput> dictionary
    
    Returns:
    chosen_pattern: the chosen placement to be deployed
    module_info: the detail deployment information
    expected_throughput: estimated throughput of the placement

    """
    all_pattern_dict_order = sorted(all_pattern_dict, key=itemgetter(-1), reverse=True)
    try:
        chosen_pattern = all_pattern_dict_order[0][0]
        module_info = all_pattern_dict_order[0][1]
        expected_throughput = all_pattern_dict_order[0][-1]
        write_out_pattern_file(all_pattern_dict_order, chosen_pattern)
    except:
        print("No available placement for this SLO\n")
        sys.exit()
    return chosen_pattern, module_info, expected_throughput


def apply_pattern(module_list, chosen_pattern, module_info, bess_para):
    """ Apply chosen placement option 'chosen_pattern' to
        all modules 'module_list' and mark the replication
        information on each module (# cores for each module)

    Parameter:
    module_list: all NF modules
    chosen_pattern: the placement to be deployed
    module_info: which hardware, # cores, which nic

    Returns:
    module_list: all NF modules notated with deployment detail

    """
    if chosen_pattern <0:
        print("no available assignment")
        sys.exit()
    total_len = len(module_list)
    for i in range(len(module_list)):
        mod_bit = (chosen_pattern>>(total_len-i-1))%2
        module_list[i].nf_type = mod_bit
        module_list[i].core_num = int(module_info[i][1])
        module_list[i].nic_index = int(module_info[i][0])
    return  module_list

def log_module(module_list):
    """ A debug/log function to store detailed NF information
    
    Parameter:
    module_list: modules to be logged

    """
    PLACE_LOGGER.info("Log module starts")
    for module in module_list:
        PLACE_LOGGER.debug("module %s, spi: %d, si: %d, nf_type %d,\
            core_num: %s, nic_index: %d, bounce: %r, merge: %r, core_index: %d", \
            module.nf_class, module.service_path_id, module.service_id, 
            module.nf_type, module.core_num, module.nic_index, 
            module.bounce, module.merge, module.core_index)
    PLACE_LOGGER.info("Log module ends")
    return

def next_optimize_pick():
    """ Read in 'pattern.txt' and pick the next best pattern.
    """
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
    return chosen_pattern, core_alloc

def count_bounce(module_list, pattern):
    """ Count # bounces between hardwares for a chain

    Paramter:
    module_list: a list of modules
    pattern: deployment placement

    Returns:
    count: number of bounces

    """
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
    """ Run no-profile algorithm (assume all BESS modules have
        same CPU cycles) and select deployment placement

    Parameter:
    pattern_list: a list of possible placements
    module_list: all NF modules
    bess_para: a dictionary of BESS moduels and its profiled
               CPU cycles
    constraints: number of available cores

    Returns:
    chosen_pattern: the selected deployment placement
    module_info: the deployment detailed info

    """
    for item_index in bess_para:
        bess_para[item_index] = '20000'

    all_chain_pattern_dict = speed_up_calc_cycle(pattern_list, \
                                                 module_list, \
                                                 bess_para, \
                                                 constraints)
    try:
        chosen_pattern, module_info, _ = optimize_pick(all_chain_pattern_dict)
    except:
        print("No placement satisfying SLO")
        sys.exit()

    
    return chosen_pattern, module_info

        

def individual_optimize_pick(module_list, bess_para, constraints):
    """ Run Greedy algortihm and select deployment placement

    Parameter:
    module_list: all NF modules
    bess_para: a dictionary of BESS moduels and its profiled
               CPU cycles
    constraints: number of available cores

    Returns:
    chosen_pattern:  the selected deployment placement
    core_num_all: a dictionary of <nic_index, core numbers>
                  for BESS modules

    """
    nic = get_nic_info()
    module_list = tag_chain_index(copy.deepcopy(module_list))
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)
    chain_rate = get_rate()
    chosen_pattern = 0
    spare_core = int(nic["nic"][0]["core"])-RESERVE_CORE

    for module in module_list:
        if module.nf_type == 2:
            module.nf_type = 0
        chosen_pattern = (chosen_pattern<<1) + module.nf_type
    
    cp_module_list = copy.deepcopy(module_list)
    chain_module_list, _ = segment_module_list(cp_module_list)
    num_of_chain = len(chain_module_list)
    final_module = []
    final_dict = {}
    usable_core = spare_core
    infeasible = False
    left_matrix = []
    right_matrix = []

    for chain_index in range(num_of_chain):
        chain_success = False
        chain_bess, chain_p4 = bfs_sort(copy.deepcopy(\
                            chain_module_list[chain_index]))
        for index in range(len(chain_bess)):
            subgroup = chain_bess[index]
            chain_bess[index] = tag_core_index(subgroup)
        if len(chain_bess) == 0:
            final_module.extend(chain_p4)
            chain_success = True
        else:
            usable_core_left = usable_core - len(chain_bess)
            if usable_core < 0:
                infeasible = True
            else:
                dup_num, dup_list, no_dup_list = count_dup(0, \
                                        range(len(chain_bess)), \
                                        copy.deepcopy(chain_bess))
                for no_dup_sublist in no_dup_list:
                    left_vector, right_const = \
                            inequal_form(no_dup_sublist, \
                                         len(chain_module_list), \
                                         bess_para)
                    left_value = max(left_vector)
                    left_matrix.append(left_vector)
                    right_matrix.append(right_const)
                    if (right_const/float(left_value) < chain_rate[chain_index][0]):                        
                        infeasible = True
                    else:
                        usable_core -= 1

                for dup_sublist in dup_list:
                    left_vector, right_const = \
                            inequal_form(dup_sublist, \
                                         len(chain_module_list), \
                                         bess_para)
                    left_value = max(left_vector)
                    find = False
                    if not_satisfy_rate(right_const/float(left_value), \
                                        chain_rate[chain_index], True):
                        used_core = 2
                        while usable_core-used_core >=0 and find == False:
                            if not not_satisfy_rate(right_const*\
                                    (used_core)/float(left_value),\
                                    chain_rate[chain_index],\
                                    True):
                                find = True
                                usable_core = usable_core - used_core

                            else:
                                used_core += 1
                        if find == False:
                            infeasible = True
                        else:
                            dup_sublist = tag_core([dup_sublist], \
                                            tuple([used_core-1]))
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
                        final_dict[dup_sublist[0].chain_index].append(\
                                        copy.deepcopy(dup_sublist))
                    final_module.extend(chain_p4)
    if not infeasible:
        indexes = sorted(final_dict)
        for key in indexes:
            if usable_core >0:
                subgroup_bottleneck = []
                for subgroup in final_dict[key]:
                    subgroup_core = subgroup[0].core_num
                    _ , right_const = inequal_form(subgroup, \
                                                   len(chain_rate), \
                                                   bess_para)
                    subgroup_bottleneck.append(right_const/float(subgroup_core))
                min_bottleneck = min(subgroup_bottleneck)
                min_index = subgroup_bottleneck.index(min_bottleneck)
                stop = False
                more_core = 0
                bottleneck_core = final_dict[key][min_index][0].core_num
                target_left, target_right = \
                    inequal_form(final_dict[key][min_index], \
                    len(chain_rate), \
                    bess_para)
                target_left_value = max(target_left)
                while not stop and usable_core-more_core >=0:
                    more_core += 1
                    adjust_rate = \
                        (target_right/float(bottleneck_core))/target_left_value
                    if not_satisfy_rate(adjust_rate*\
                            (bottleneck_core+more_core), \
                            chain_rate[key-1], \
                            False):
                        stop = True
                tmp_list = tag_core([final_dict[key][min_index]], \
                                tuple([bottleneck_core-1+more_core-1]))
                final_dict[key][min_index] = tmp_list[0]
                usable_core = usable_core - (more_core-1)
            for sub_dup in final_dict[key]:
                final_module.extend(sub_dup)
        final_module.sort(key=lambda l: (l.service_path_id, l.service_id))
        tmp_module_list = copy.deepcopy(module_list)
        tmp_module_list = tag_from_notated_list(tmp_module_list, \
                                                final_module)
        bess_subgroup_list, p4_list = bfs_sort(tmp_module_list)
        left_matrix = []
        right_matrix = []
        for sub_list in bess_subgroup_list:
            left_vector, right_const = \
                            inequal_form(sub_list, \
                                         len(chain_module_list), \
                                         bess_para)
            left_matrix.append(left_vector)
            right_matrix.append(right_const)
        sum_of_left_traffic = [0]*len(chain_module_list)
        sum_of_left_traffic = (np.sum(left_matrix, axis=0)).tolist()
        left_matrix.append(sum_of_left_traffic)
        right_matrix.append(int(nic["nic"][int(0)]["throughput"])*1000000)
        left_matrix = np.array(left_matrix)
        right_matrix = np.array(right_matrix)
        t = maximizeMarginalRate(chain_rate, left_matrix, right_matrix)
        mr =  marginalRate(chain_rate, t)
        module_list = tag_from_notated_list(module_list, final_module)
    else:
        print "infeasible to match min_requirement"
    
    core_num_all = []
    for module in module_list:
        core_num_all.append([module.nic_index, module.core_num])


    return chosen_pattern, core_num_all    

def all_p4_optimize_pick(pattern_list, module_list, bess_para):
    """ Run HW-preferred algorithm and select deployment placement

    Parameter:
    pattern_list: a list of possible placements
    module_list: all NF modules
    bess_para: a dictionary of BESS moduels and its profiled
               CPU cycles
    
    Returns:
    chosen_pattern: the selected deployment placement
    core_num_all: a dictionary of <nic_index, core numbers>
                  for BESS modules
    """
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)

    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    chosen_pattern = 0
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
    dup_num, dup_list, no_dup_list = \
            count_dup(0, range(len(bess_subgroup_list)), \
            copy.deepcopy(bess_subgroup_list))
    chain_indexes = []
    for sub_list in dup_list:
        chain_indexes.append(sub_list[0].chain_index)
    unique_entries = set(chain_indexes)
    categorize_dict = {}
    for entry in unique_entries:
        categorize_dict[entry] = []
    nic = get_nic_info()
    spare_core_num = int(nic["nic"][0]["core"])\
                        -RESERVE_CORE\
                        -len(bess_subgroup_list)
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
                _ , right_const = inequal_form( subgroup, \
                                                total_chain_num, \
                                                bess_para)
                subgroup_bottleneck.append(right_const)
            min_bottleneck = min(subgroup_bottleneck)
            min_index = subgroup_bottleneck.index(min_bottleneck)
            dup_matrix = [0]*len(subgroup_bottleneck)
            dup_matrix[min_index] = each_chain_core
            dup_tuple = tuple(dup_matrix)
            categorize_dict[chain_index] = \
                    tag_core(categorize_dict[chain_index], dup_tuple)
            for subgroup in categorize_dict[chain_index]:
                notated_final.extend(subgroup)
                left_vector, right_const = \
                    inequal_form(subgroup, total_chain_num, bess_para)
                left_matrix.append(left_vector)
                right_matrix.append(right_const)
    for sub_list in no_dup_list:
        notated_final.extend(sub_list)
        left_vector, right_const = inequal_form(sub_list, \
                                                total_chain_num, \
                                                bess_para)
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
    module_list = tag_from_notated_list(module_list, notated_final)
    core_num_all = []
    for module in module_list:
        core_num_all.append([module.nic_index, module.core_num])

    return chosen_pattern, core_num_all

def all_BESS_optimize_pick(pattern_list, module_list, bess_para, constraints):
    """ Run SW-preferred algorithm and select deployment placement

    Parameter:
    pattern_list: a list of possible placements
    module_list: all NF modules
    bess_para: a dictionary of BESS moduels and its profiled
               CPU cycles
    constraints: number of available cores
    
    Returns:
    chosen_pattern: the selected deployment placement
    core_num_all: a dictionary of <nic_index, core numbers>
                  for BESS modules
    """
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
    dup_num, dup_list, no_dup_list = \
            count_dup(0, range(len(bess_subgroup_list)), \
                        copy.deepcopy(bess_subgroup_list))
    chain_indexes = []
    for sub_list in dup_list:
        chain_indexes.append(sub_list[0].chain_index)
    unique_entries = set(chain_indexes)
    categorize_dict = {}
    for entry in unique_entries:
        categorize_dict[entry] = []
    nic = get_nic_info()
    spare_core_num = int(nic["nic"][0]["core"])\
                        -RESERVE_CORE\
                        -len(bess_subgroup_list)
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
                _ , right_const = inequal_form( subgroup, \
                                                total_chain_num, \
                                                bess_para)
                subgroup_bottleneck.append(right_const)
            min_bottleneck = min(subgroup_bottleneck)
            min_index = subgroup_bottleneck.index(min_bottleneck)
            dup_matrix = [0]*len(subgroup_bottleneck)
            dup_matrix[min_index] = each_chain_core
            dup_tuple = tuple(dup_matrix)
            categorize_dict[chain_index] = \
                tag_core(categorize_dict[chain_index], dup_tuple)
            for subgroup in categorize_dict[chain_index]:
                notated_final.extend(subgroup)
                left_vector, right_const = inequal_form(subgroup, \
                                                        total_chain_num, \
                                                        bess_para)
                left_matrix.append(left_vector)
                right_matrix.append(right_const)
    for sub_list in no_dup_list:
        notated_final.extend(sub_list)
        left_vector, right_const = inequal_form(sub_list, \
                                                total_chain_num, \
                                                bess_para)
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
    module_list = tag_from_notated_list(module_list, notated_final)
    core_num_all = []
    for module in module_list:
        core_num_all.append([module.nic_index, module.core_num])

    return chosen_pattern, core_num_all


def no_core_alloc_optimization_pick(pattern_list, module_list, bess_para): 
    """ Run no core allocation algorithm and select deployment placement

    Parameter:
    pattern_list: a list of possible placements
    module_list: all NF modules
    bess_para: a dictionary of BESS moduels and its profiled
               CPU cycles
    
    Returns:
    chosen_pattern: the selected deployment placement
    chosen_tuple: a tuple of # cores for each subgroup
    """
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
    """ Run min bounce allocation algorithm and select deployment placement

    Parameter:
    pattern_list: a list of possible placements
    module_list: all NF modules
    bess_para: a dictionary of BESS moduels and its profiled
               CPU cycles
    
    Returns:
    chosen_pattern: the selected deployment placement
    chosen_tuple: a tuple of # cores for each subgroup
    """
    module_list = tag_chain_index(module_list)
    weight_dict = generate_weight(module_list)
    module_list = tag_weight(module_list, weight_dict)
    chain_rate = get_rate()
    total_chain_num = len(chain_rate)
    pattern_dict = []

    for pattern in pattern_list:
        notated_list = copy.deepcopy(module_list)
        total_module_num = len(module_list)
        for module_index in range(total_module_num):
            mode_bit = (pattern>>(total_module_num - module_index-1))%2
            notated_list[module_index].nf_type = mode_bit


        bess_subgroup_list, p4_list = bfs_sort(notated_list)
         
        for index in range(len(bess_subgroup_list)):
            subgroup = bess_subgroup_list[index]
            bess_subgroup_list[index] = tag_core_index(subgroup)
        dup_num, dup_list, no_dup_list = \
                count_dup(0, range(len(bess_subgroup_list)), \
                            copy.deepcopy(bess_subgroup_list))
        subgroup_count = len(no_dup_list)+len(dup_list)
        chain_indexes = []
        for sub_list in dup_list:       
            chain_indexes.append(sub_list[0].chain_index)
        unique_entries = set(chain_indexes)
        categorize_dict = {}
        for entry in unique_entries:
            categorize_dict[entry] = []
        nic = get_nic_info()
        spare_core_num = int(nic["nic"][0]["core"])\
                            -RESERVE_CORE\
                            -len(bess_subgroup_list)
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
                    left_vector , right_const = \
                        inequal_form(subgroup, total_chain_num, bess_para)
                    left_value = float(max(left_vector))
                    subgroup_bottleneck.append(right_const/float(left_value))
                min_bottleneck = min(subgroup_bottleneck)
                min_index = subgroup_bottleneck.index(min_bottleneck)
                dup_matrix = [0]*len(subgroup_bottleneck)
                dup_matrix[min_index] = each_chain_core
                dup_tuple = tuple(dup_matrix)
                categorize_dict[chain_index] = \
                    tag_core(categorize_dict[chain_index], dup_tuple)
                for subgroup in categorize_dict[chain_index]:
                    notated_final.extend(subgroup)
                    left_vector, right_const = \
                        inequal_form(subgroup, total_chain_num, bess_para)
                    left_matrix.append(left_vector)
                    right_matrix.append(right_const)
        for sub_list in no_dup_list:
            notated_final.extend(sub_list)
            left_vector, right_const = \
                    inequal_form(sub_list, total_chain_num, bess_para)
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
        for module in notated_final:
            if module.nf_type == 0:
                assert module.nic_index == -1
            else:
                assert module.nic_index == 0
            core_num_all.append([module.nic_index, module.core_num])
        pattern_dict.append([pattern, core_num_all, mr, -subgroup_count])

    all_pattern_dict_order = sorted(pattern_dict, key=itemgetter(-1, -2), reverse=True)   
    chosen_pattern = all_pattern_dict_order[0][0]
    module_info  = all_pattern_dict_order[0][1]

    return chosen_pattern, module_info
    

def mode_select_pattern_list(mode, module_list):
    """ Enumerate all possible placement for each mode
    
    Parameter:
    mode: chosen algorithm number
    module_list: all NF modules

    Returns:
    pattern_list: all possible placement

    """
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

def heuristic_core_allocation(module_list):
    """ Run brutal force routine for heuristic's 
        core allocation

    Parameter:
    module_list: all NF modules

    Returns:
    all_chain_pattern_dict: <pattern, throughput> dictionary
    bess_dict_para: a dictionary of BESS moduels and its profiled
                    CPU cycles

    """

    pattern_list = enum_case(module_list)
    bess_dict_para, constraints = read_para()

    all_chain_pattern_dict = speed_up_calc_cycle(pattern_list, \
                                                 module_list, \
                                                 bess_dict_para, \
                                                 constraints)

    return all_chain_pattern_dict, bess_dict_para

def mode_select_hardware_deployment(mode, chain_enum_list, 
                    all_modules, bess_dict_para, constraints):
    """ Select from possible placement and run algorithm
        to decide the best placement and core assignment

    Parameter:
    mode: chosen algorithm number
    chain_enum_list: all possible placement
    all_modules: all NF modules
    bess_dict_para: a dictionary of bess module name and 
                    profiled cycles
    constraints: number of available BESS cores in total

    Returns:
    chosen_pattern: selected deployment hardware decision
    core_alloc: number of cores assigned for each BESS
                NF instances
    """
    chosen_pattern = -1
    core_alloc = None

    if mode == 0 or mode == 6:
        all_chain_pattern_dict = speed_up_calc_cycle(chain_enum_list,\
                             all_modules, bess_dict_para, constraints)
        chosen_pattern, core_alloc, _ = optimize_pick(all_chain_pattern_dict)
    elif mode == 1:
        chosen_pattern, core_alloc = no_profile_optimize_pick(chain_enum_list,\
                                     all_modules, bess_dict_para, constraints)
    elif mode == 2:
        chosen_pattern, core_alloc = individual_optimize_pick( all_modules, \
                                                bess_dict_para, constraints)
    elif mode == 3:
        chosen_pattern, core_alloc = all_p4_optimize_pick(chain_enum_list, \
                                                all_modules, bess_dict_para)
    elif mode == 4:
        all_chain_pattern_dict = no_core_op_calc_cycle(chain_enum_list, \
                                                all_modules, bess_dict_para)
        chosen_pattern, core_alloc = optimize_pick(all_chain_pattern_dict)
    elif mode == 5:
        chosen_pattern, core_alloc = E2_optimization_pick(chain_enum_list, \
                                                all_modules, bess_dict_para)
    elif mode == 7:
        chosen_pattern, core_alloc = all_BESS_optimize_pick(chain_enum_list, \
                                    all_modules, bess_dict_para, constraints)
        
    return chosen_pattern, core_alloc

def place_decision(lemur_parser, next_best_flag, op_mode):
    """ Run chosen algorithm to assign deploymenet hardware

    Parameter:
    lemur_parser: DAG parser
    next_best_flag: flagged to chose next best placement
    op_mode: chosen algorithm

    Returns:
    all_modules: all marked NFs with assigned deployment info
    
    """
    decision_pattern = None
    bess_cycle_profile_dict = {}
    constraints = {}
    all_modules = []
    modules = []
    
    nf_graph = convert_global_nf_graph(lemur_parser.scanner)
    modules = nf_graph.list_modules()
    modules.sort(key=lambda l: (l.service_path_id, l.service_id))
    bess_cycle_profile_dict, constraints = read_para()

    if not next_best_flag:
        chain_enum_list = mode_select_pattern_list(op_mode, modules)
        decision_pattern, core_alloc = mode_select_hardware_deployment(op_mode, \
                chain_enum_list, modules, bess_cycle_profile_dict, constraints)
    else:
        decision_pattern, core_alloc = next_optimize_pick()

    all_modules = apply_pattern(modules, decision_pattern, core_alloc, \
                                bess_cycle_profile_dict)
    if all_modules:
        log_module(all_modules)
    else:
        warnings.warn("no available placement")
    return all_modules

if __name__ == "__main__":
    place_decision()
