"""
NEW_BESS_GENERATOR.PY
This script converts NF chain graph into BESS code pipelines

Author: Jane Yen
Time: 12/05/2018
Email: yeny@usc.edu
"""
import os
import copy
from nf_placement import get_nic_info, bfs_sort
from nf_placement import log_module
from lemur_bess_generator_util import class_and_arg, new_gate_add, new_branch_add


def script_template(nic):
    SERVER_PCI = nic["pci"]
    NIC_NAME = nic["name"]
    NIC_CORE = nic["core"]
    bess_filename = "%s.bess" % NIC_NAME
    bess_fp = open(bess_filename, 'w')
    PRECOMPUTE_LINE = ("%s_nsh::NSHdecap()\n%s_myport=PMDPort(pci=\'%s\')\n" % (NIC_NAME, NIC_NAME, SERVER_PCI))
    bess_fp.write(PRECOMPUTE_LINE)
    PORTIN_LINE = "%s_pin::PortInc(port=%s_myport) -> %s_nsh\n" % (NIC_NAME, NIC_NAME, NIC_NAME)
    bess_fp.write(PORTIN_LINE)
    PORTOUT_LINE = "%s_queue::Queue() -> %s_pout::PortOut(port=%s_myport)\n" % (NIC_NAME, NIC_NAME, NIC_NAME)
    bess_fp.write(PORTOUT_LINE)
    CORE_LINE = ("for i in range(%d):\n\tbess.add_worker(i,i)\n" % int(NIC_CORE))
    bess_fp.write(CORE_LINE)
    bess_fp.write('\n')
    return bess_filename

def set_bounce(module_list):
    
    initial_pick = True
    for module in module_list:
        if initial_pick and module.is_bess():
            module.bounce = True
            initial_pick = False
        if len(module.adj_nodes) == 0:
            initial_pick = True
        for adj_node in module.adj_nodes:
            if adj_node.is_bess() and adj_node.nf_type != module.nf_type:
                adj_node.bounce = True
    return module_list

def def_instance(module, nfcp_parser):
    instance_def = []
    if module.nf_class != "TrafficShaper":
#        instance_def.append("%s = %s" % (module.name, "Queue()"))
#        instance_def.append("bess.add_tc('%s_tc', policy='rate_limit', resource='bit', max_burst={'bit': 100000000000}, limit={'bit': 100000000000})" % module.name)
#        instance_def.append("%s.attach_task(parent='%s_tc')" % (module.name, module.name))
#    else:
        instance_def.append("%s = %s" % (module.name, class_and_arg(module, nfcp_parser)))
    return instance_def

def nsh_connection(module, gate_index, extra_queue_index, nic_name):
    connection = ("%s_nsh:%d ->q%d_extra::Queue()-> %s" % (nic_name, gate_index, extra_queue_index, module.name))
    return connection

def ts_exist(subgroup):
    exist_flag = False
    ts_str = ""
#    print subgroup
    for module in subgroup:
#        print "nope"
        if module.nf_class == "TrafficShaper":
            exist_flag = True
            ts_str = module.name
    return exist_flag, ts_str

def nic_pipeline(list_of_subgroup, nfcp_parser, nic_name):
    return_str = []
    gate_index = 0
    rr_index = 0
    queue_index = 1    # Don't touch core 0
    extra_queue_index = 0
    #bpf_index = 0
    copy_list_of_subgroup = copy.deepcopy(list_of_subgroup)
    for subgroup in copy_list_of_subgroup:
        # define all modules at the beginning
        for module in subgroup:
            return_str.extend(def_instance(module, nfcp_parser))

        # define nsh gate
        for module in subgroup:
            if module.bounce:
                return_str.append(new_gate_add(module, gate_index,nic_name))
                if module != subgroup[0]:
                    return_str.append(nsh_connection(module, gate_index, extra_queue_index, nic_name))
                    return_str.append("q%d_extra.attach_task(wid=%d)" % (extra_queue_index, queue_index))
                    extra_queue_index += 1
                module.nsh_gate = gate_index
                gate_index += 1
#            print module.nf_class
#        print subgroup

        # check if there's traffic control in the subgroup
        TS_FLAG, TS_STR = ts_exist(copy.deepcopy(subgroup))

        # define subgroup connection
        root_module = subgroup[0]
        if root_module.core_num > 1:
            rr_def = ("%s_nsh:%d  -> rr%d::RoundRobin(gates=range(%d))" % (nic_name, root_module.nsh_gate, rr_index, root_module.core_num))
            return_str.append(rr_def)
#            return_str.append('q%d.attach_task(wid=%d)' % (queue_index, queue_index))
#            queue_index += 1
            concate_str = ""
            for module in subgroup:
                if module.nf_class != "TrafficShaper":
                    concate_str += (" -> %s" % class_and_arg(module, nfcp_parser))
                if module.adj_nodes[0].is_p4():
                    concate_str += '->NSHencap(new_spi=\'%d\', new_si=\'%d\')->%s_queue' % (module.adj_nodes[0].service_path_id, module.adj_nodes[0].service_id, nic_name)
            for rr_gate in range(root_module.core_num):
                return_str.append("rr%d:%d -> q%d::Queue() %s" % (rr_index,rr_gate, queue_index, concate_str))
                if TS_FLAG:
                    return_str.append("bess.add_tc('%s_tc', policy='rate_limit', resource='bit', max_burst={'bit': 100000000000}, limit={'bit': 100000000000}, wid=%d)" % (TS_STR, queue_index))
                    return_str.append("q%d.attach_task(parent='%s_tc')" % (queue_index, TS_STR))
                else:
                    return_str.append('q%d.attach_task(wid=%d)' % (queue_index, queue_index))
                queue_index += 1
            rr_index += 1
        else:
            if root_module.nf_class != "TrafficShaper":
                return_str.append("%s_nsh:%d -> q%d::Queue() -> %s" % (nic_name, root_module.nsh_gate, queue_index, root_module.name))
            else:
                return_str.append("%s_nsh:%d -> q%d::Queue()" % (nic_name, root_module.nsh_gate, queue_index))
            if TS_FLAG:
                return_str.append("bess.add_tc('%s_tc', policy='rate_limit', resource='bit', max_burst={'bit': 100000000000}, limit={'bit': 100000000000}, wid=%d)" % (TS_STR, queue_index))
                return_str.append("q%d.attach_task(parent='%s_tc')" % (queue_index, TS_STR))
            else:
                return_str.append('q%d.attach_task(wid=%d)' % (queue_index, queue_index))
            queue_index += 1
            output_str = ""
            pop_queue = []
            first_child_flag = False
            while len(subgroup) >0:
                if first_child_flag == False:
                    cur_module = subgroup.pop(0)
                else:
                    first_child_flag = False
                if cur_module in pop_queue:
                    continue
                if len(output_str) == 0 and cur_module.nf_class != "TrafficShaper":
                    output_str = cur_module.name
                elif len(output_str) == 0 and cur_module.nf_class == "TrafficShaper":
                    output_str = 'q%d' % (queue_index-1)
                else:
                    if cur_module.nf_class != "TrafficShaper":
                        output_str += ("-> %s" % cur_module.name)
                pop_queue.append(cur_module)
                if len(cur_module.branch_str)>0:
                    return_str.append("%s -> %s" % (cur_module.branch_str, cur_module.name))

                if len(cur_module.adj_nodes)>1:
                    output_str, transit_condition, _ = new_branch_add(cur_module, output_str)
                    #return_str.append(bpf_def)
                    return_str.append(output_str)
                    return_str.append(transit_condition)
                    output_str = ""

                    cur_module = cur_module.adj_nodes[0]
                    first_child_flag = True
                else:
                    if cur_module.adj_nodes[0].is_p4() or cur_module.adj_nodes[0].is_smartnic():
                        output_str += ('->NSHencap(new_spi=\'%d\', new_si=\'%d\')->%s_queue' % (cur_module.adj_nodes[0].service_path_id, cur_module.adj_nodes[0].service_id, nic_name))
                        return_str.append(output_str)
                        output_str = ""
                    else:
                        if cur_module.adj_nodes[0] not in pop_queue:
                            cur_module = cur_module.adj_nodes[0]
                            first_child_flag = True
                        else:
                            if cur_module.adj_nodes[0].nf_class != "TrafficShaper":
                                output_str += ("-> %s " % cur_module.adj_nodes[0].name)
                            return_str.append(output_str)
                            output_str = ""
                                                                          
        return_str.append("\n")
    return_str.append("%s_pin.attach_task(wid=%d)" % (nic_name, 0))
    return_str.append("%s_queue.attach_task(wid=%d)" % (nic_name, queue_index))

    return return_str       

def generate_bess(nfcp_parser, module_list):
    
    nic_info = get_nic_info()
    nic = nic_info["nic"]
    filename_list = []

    nic_subgroup_map = []
    for i in range(len(nic)):
        filename = script_template(nic[i])
        filename_list.append(filename)
        nic_subgroup_map.append([])

    module_list = set_bounce(module_list)
    log_module(module_list)
    bess_subgroup_list, _ = bfs_sort(module_list)

    for sub_list in bess_subgroup_list:
        nic_index = sub_list[0].nic_index
        nic_subgroup_map[nic_index].append(sub_list)

    for index in range(len(nic)):
        str_list = []
        if len(nic_subgroup_map[index])>0:
#            str_list,_, _, _, _, _, _ = \
#                new_setup_pipeline(nic_subgroup_map[index], nfcp_parser, 0, 0, 0, 0, 0)
            str_list = nic_pipeline(nic_subgroup_map[index], nfcp_parser, filename_list[index].split('.')[0])
#        print(filename_list[index])
        
        fp = open(filename_list[index], 'a')
        for line in str_list:
            fp.write(line)
            fp.write('\n')
        fp.close()
    
    return
