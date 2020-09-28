
"""
* Title: nfcp_nf_node.py
* Description:
* This file defines the 'class nf_node' data structure. 
* Each node represents a network function module in the network function chain graph.
* In order to manipulate each NF ndoe, a set of methods are provided by this library.
* 
* Author: Jianfeng Wang
* Time: 02/26/2018
* Email: jianfenw@usc.edu
*
"""

from __future__ import print_function
import copy
import re

"""
The three module lists record all P4 (p4-14 and p4-16) modules, and BESS modules.
"""
global bess_module_list
global p4_module_list
global p4_14_module_list
global dup_avoid_list

"""
The five states are used to decide where to place each NSHEncap (P4) node.
Please check get_p4_nodes(), get_p4_nodes_helper() to see the details.
"""
global S_ROOT_STARTER
global S_P4
global S_ROOT_BESS
global S_NON_ROOT_BESS
global S_NON_ROOT_BESS_CONT

dup_avoid_list = [\
    "TrafficShaper", \
    "NAT"
]

bess_module_list = ["MACSwap", \
    "ACL", \
    "AESCBC", \
    "UpdateTTL", \
    "Update", \
    "ECHO", \
    "VLANPush", \
    "VLANPop", \
    "EncryptUDP", \
    "HashLB", \
    "NAT",\
    "BPF",\
    "UrlFilter",\
    "TrafficShaper",\
    "AESCBCde",\
    "Measure",\
    "DEDUP"]

p4_module_list = {
    'SYS' : 'sys.lib', \
    'ACL': 'acl.lib', \
    'SilkRoad': 'silkroad.lib', \
    'IPv4Forward': 'ipv4_forward.lib', \
    'NSHEncap': 'send_to_bess.lib', \
    #'SimpleNAT': 'nat_stan.lib', \
    "HashLB": 'hash_lb.lib', \
    'NAT': 'nat_stan.lib', \
    'P4UpdateTTL': 'update_ttl_p4.lib', \
    'UpdateTTL': 'update_ttl_p4.lib', \
    #'VLANADD': 'vlan_add.lib', \
    'VLANPush': 'vlan_add.lib', \
    'VLANPop': 'vlan_rm.lib', \
    'Drop': 'drop.lib',\
    'Dummy': 'dummy.lib',\
    'PktFilter' : 'pfilter.lib'}

p4_14_module_list = {
    'SYS' : 'sys.lib', \
    'ACL' : 'acl.lib', \
    'SilkRoad' : 'silkroad.lib', \
    'IPv4Forward' : 'ipv4_forward.lib', \
    'P4UpdateTTL': 'update_ttl_p4.lib', \
    'UpdateTTL': 'update_ttl_p4.lib', \
    #'SimpleNAT': 'simple_nat.lib', \
    "HashLB": 'hash_lb.lib', \
    'NAT': 'simple_nat.lib', \
    #'NAT': 'nat_reduce.lib', \
    #'VLANADD': 'vlan_add.lib', \
    'VLANPush': 'vlan_add.lib', \
    'VLANPop': 'vlan_rm.lib', \
    'NSHEncap' : 'send_to_bess.lib', \
    'DROP' : 'drop.lib',\
    'Dummy': 'dummy.lib',\
    'PktFilter' : 'pfilter.lib'}

S_ROOT_STARTER=0
S_P4=1
S_ROOT_BESS=2
S_NON_ROOT_BESS=3
S_NON_ROOT_BESS_CONT=4

class nf_chain_graph(object):
    """
    Description: the NF chain graph class. 
    This class represents a single NF chain input. Each NF chain graph should match a flowspec.
    Call convert_nf_graph(ll_node) to convert a ll_node into a NF chain graph instance.
    """
    def __init__(self, flowspec_instance):
        self.module_list = {}
        self.module_num = 0
        self.flowspec = None
        self.is_feasible_p4 = False
        # self.heads contains all nodes that does not have parent nodes
        # self.tails contains all nodes that does not have child nodes
        self.heads = []
        self.tails = []
        self.spi_list = None
        if flowspec_instance != None:
            self.set_flowspec(flowspec_instance)

        # for topo sort (DFS method)
        self.curr_finish_time = 0
        self.p4_nodes = None
        self.bess_nodes = None
        return

    def set_flowspec(self, flowspec_instance):
        self.flowspec = copy.deepcopy(flowspec_instance)
        return

    def add_module(self, target_node):
        module_key = target_node.name
        new_nf_node = nf_node()
        new_nf_node.setup_node_from_nf_node(target_node)
        if module_key not in self.module_list:
            self.module_list[module_key] = new_nf_node
            self.heads.append(new_nf_node)
            self.tails.append(new_nf_node)
            self.module_num += 1
        else:
            if self.module_list[module_key] != new_nf_node:
                self.module_list[module_key].update_shared_module(new_nf_node)
        return

    def get_module(self, module_key):
        if module_key in self.module_list.keys():
            return self.module_list[module_key]
        else:
            return None

    def add_edge(self, src, dst):
        """ Description: add a edge between two nf_node instances. 
        If nf_node does not exist, then add the node first
        Input: src, dst (type(src), type(dst) == nf_node)
        Output: None
        """
        #print('add edge(%s -> %s)' %(src.name, dst.name))
        self.add_module(src)
        src = self.module_list[src.name]
        self.add_module(dst)
        dst = self.module_list[dst.name]

        if src in self.tails: # src is a new parent
            self.tails.remove(src)
        if dst in self.heads: # dst is a new child
            self.heads.remove(dst)
        src.add_neighbor(dst)
        return

    def del_edge(self, src, dst):
        """ Description: delete the edge between two nf_node instances.
        :type src: nf_node
        :type dst: nf_node
        :rtype: None
        """
        src = self.module_list[src.name]
        dst = self.module_list[dst.name]
        src.adj_nodes.remove(dst)
        dst.prev_nodes.remove(src)
        if dst in self.tails:
            self.tails.remove(dst)
            self.tails.append(src)
        if len(dst.prev_nodes) == 0: # dst should be removed
            self.module_num -= 1
            self.module_list.pop(dst.name)

    def list_modules(self):
        #print('Len module list:%d, module #:%d' %(len(self.module_list), self.module_num))
        return self.module_list.values()

    def verify_graph(self):
        """
        Description: verify the graph is correctly generated
        Input: None
        Output: Bool
        """
        assert (len(self.module_list) == self.module_num)
        # check whether children are found in self.module_list
        for nf_name, nf_node in self.module_list.items():
            for next_node in nf_node.adj_nodes:
                if next_node not in self.module_list.values():
                    assert (next_node == self.module_list[next_node.name])
        return

    def __iter__(self):
        return iter(self.module_list.values())

    def __contains__(self, target_node):
        return (target_node.name in self.module_list)

    def check_shared_modules(self):
        """
        Description: this function will check whether any infeasible placement of shared modules exists in the NF chain.
        We run this algorithm for each NF chain seperately because shared modules are always legal across NF chains.
        """
        print('NF Graph: check shared modules', self.flowspec )
        '''
        # check whether there is any loop for all P4 nodes
        print(len(self.heads))
        for node in self.module_list.values():
            print(node.name, node.shared_spi_list, node.visited)
        for starter in self.heads:
            print(starter)
            self.is_feasible_p4 = self.check_shared_modules_helper(starter)
        print(self.is_feasible_p4)
        for node in self.module_list.values():
            print(node.name, node.shared_spi_list, node.visited)
        return self.is_feasible_p4
        '''
        return False

    def check_shared_modules_helper(self, node):
        if node.visited:
            if node.is_p4():
                return False
            else:
                return True
        node.visited = 1
        for next_node in node.adj_nodes:
            if not self.check_shared_modules_helper(next_node):
                return False
        return True

    def get_sp_count(self):
        """
        This function returns the number of service chains for the graph.
        Input: None
        Output: count (type=int)
        """
        if self.spi_list != None:
            return len(self.spi_list)

        self.spi_list = []
        for starter in self.heads:
            self.get_sp_count_helper(starter)
        return len(self.spi_list)

    def get_sp_count_helper(self, node):
        if node.service_path_id not in self.spi_list:
            self.spi_list.append(node.service_path_id)
        # process the next nodes
        for next_node in node.adj_nodes:
            self.get_sp_count_helper(next_node)
        return

    def get_p4_nodes(self):
        if self.p4_nodes != None:
            return self.p4_nodes
        self.p4_nodes = []
        for starter in self.heads:
            self.get_p4_nodes_helper(starter, S_ROOT_STARTER, 1, 0, 0)
        return self.p4_nodes

    def get_p4_nodes_helper(self, node, prev_node_status, is_entry, layer, index):
        """
        Description:
        This is the helper function for the get_p4_nodes().
        Input: node(type=nf_node), node_status(type=Int)
        Output: None
        """
        global global_traverse_time
        # Decide curr_node_status
        #S_ROOT_STARTER=0
        #S_P4=1
        #S_ROOT_BESS=2
        #S_NON_ROOT_BESS=3
        #S_NON_ROOT_BESS_CONT=4
        curr_node_status = -1
        p4_status = [S_P4]
        bess_status = [S_ROOT_BESS, S_NON_ROOT_BESS, S_NON_ROOT_BESS_CONT]
        bess_transition_matrix={ S_ROOT_STARTER: S_ROOT_BESS, \
            S_P4: S_NON_ROOT_BESS, S_ROOT_BESS: S_NON_ROOT_BESS_CONT, \
            S_NON_ROOT_BESS: S_NON_ROOT_BESS_CONT, S_NON_ROOT_BESS_CONT: S_NON_ROOT_BESS_CONT}

        # we have processed this node (the 'merge' node = P4 / BESS root node)
        for p4_node in self.p4_nodes: # either S_P4 or S_ROOT_BESS
            if p4_node.service_path_id==node.service_path_id and p4_node.service_id==node.service_id:
                return
        if node.is_p4():
            curr_node_status = S_P4
        elif node.is_bess():
            curr_node_status = bess_transition_matrix[prev_node_status]
        else:
            error_msg = "Error: %s has a wrong nf_node type %s" %(node.name, node.nf_class)
            raise Exception(error_msg)

        # In S_NON_ROOT_BESS_CONT(4) case, target_node = None
        target_node = None
        if curr_node_status==S_P4:
            target_node = copy.deepcopy(node)
        elif curr_node_status==S_ROOT_BESS:
            if prev_node_status==S_ROOT_STARTER or prev_node_status==S_P4:
                # add a NSH node
                target_node = nf_node()
                target_node.setup_node_from_argument('nsh_%d_%d' %(node.service_path_id, node.service_id), \
                    'NSHEncap', node.service_path_id, node.service_id)
        elif curr_node_status==S_NON_ROOT_BESS:
            target_node = nf_node()
            target_node.setup_node_from_argument('nsh_%d_%d' %(node.service_path_id, node.service_id), \
                    'NSHEncap', node.service_path_id, node.service_id)
        # Here we set up the NF selection and handle branching for the P4 code generation
        # (1) update next nf_node selection
        # (2) compute the control flow layer and index
        if target_node:
            target_node.entry_flag = is_entry
            target_node.control_flow_layer = layer
            target_node.control_flow_idx = index
            if len(node.adj_nodes) != 0: # node with adj_nodes
                '''
                if curr_node_status == S_P4:
                    print('P4 node:', len(node.adj_nodes), next_node, next_node.transition_condition)
                '''
                for next_node in node.adj_nodes:
                    target_node.next_nf_selection.append((next_node.transition_condition, next_node.service_path_id, next_node.service_id))
            self.p4_nodes.append(target_node)

        # next_node_entry: the flag that indicates whether the next node sees the entry (control_flow_graph)
        next_node_entry = 0
        is_first_nf = True
        if target_node:
            if target_node.is_nshencap():
                next_node_entry = 1
        else:
            if curr_node_status==S_NON_ROOT_BESS_CONT:
                next_node_entry = 1
        next_node_layer = layer + int(len(node.adj_nodes)>1)
        next_node_index = 0
        next_node_index_list = []
        for idx, next_node in enumerate(node.adj_nodes):
            if is_first_nf:
                if next_node.is_nshencap():
                    next_node_index_list.append(-1)
                else:
                    next_node_index_list.append(0)
                    is_first_nf=False
            else:
                if next_node.is_nshencap():
                    next_node_index_list.append(-1)
                else:
                    next_node_index_list.append(1)
        
        for idx, next_node in enumerate(reversed(node.adj_nodes)):
            self.get_p4_nodes_helper(next_node, curr_node_status, next_node_entry, next_node_layer, next_node_index_list[len(node.adj_nodes)-idx-1])

        if target_node:
            target_node.finish_time = self.curr_finish_time
        self.curr_finish_time += 1
        return


class nf_node(object):
    """
    Note:
    nf_type = -1 -> Invalid module
    nf_type = 0 -> P4 module; 
    nf_type = 1 -> BESS module;
    nf_type = 2 -> either P4 or BESS;
    """
    def __init__(self, ll_node=None):
        # self.name = network function instance's name
        # self.nf_class = network function's name
        # self.adj_nodes = a list of nodes which has the current node as its parent
        self.name = None
        self.nf_class = None
        self.nf_type = -1
        self.service_path_id = -1
        self.service_id = -1
        self.shared_spi_list = []
        self.transition_condition = None
        self.argument = None
        if ll_node != None:
            self.setup_node_from_ll_node(ll_node)
        # connection_status:
        # 1. self.is_parent: the node is a parent node of another node
        # 2. self.is_child: the node is a child node of another node
        #self.is_parent = False
        #self.is_child = False
        self.prev_nodes = []
        self.adj_nodes = []
        self.next_nf_selection = []
        self.nf_select_tables = []
        self.entry_flag = -1
        self.control_flow_layer = -1
        self.control_flow_idx = -1

        # topo sort
        self.finish_time = -1
        self.visited = 0

        self.core_num = 1
        self.nsh_gate = -1
        self.bpf_gate = -1
        self.nic_index = -1
        self.chain_index = 0
        self.optimize = False
        self.reset = False
        self.branch_str = ''
        self.arg = None
        self.bounce = False
        self.parent_count = 0
        self.merge = False
        self.core_index = -1
        self.weight = 0
        self.macro_list = None
        self.const_list = None
        self.header_list = None
        self.metadata_dict = None
        self.parser_states = None
        self.output_prefix = None
        self.field_lists = None
        self.field_list_calcs = None
        self.action_prefix = None
        self.table_prefix = None
        self.ingress_actions = None
        self.ingress_tables = None
        self.ingress_apply_rules = None
        self.egress_code = None
        self.deparser_header_list = None
        return

    def setup_node_from_argument(self, nf_name, nf_class, spi, si):
        if nf_name != None:
            self.name = copy.deepcopy(nf_name)
        self.nf_class = copy.deepcopy(nf_class)
        self.service_path_id = spi
        self.service_id = si
        self.setup_node_nf_type()
        return

    def setup_node_from_ll_node(self, ll_node):
        self.name = ll_node.instance
        self.nf_class = ll_node.instance_nf_class
        self.setup_node_nf_type()
        self.service_path_id = ll_node.spi
        self.service_id = ll_node.si
        self.transition_condition = copy.deepcopy(ll_node.transition_condition)
        self.argument = copy.deepcopy(ll_node.argument)
        return

    def setup_node_from_nf_node(self, nf_node):
        """
        Description: create a standalone copy of the target_node. The new node
        does not have transition_condition. It also has empty adj_nodes.
        """
        self.name = nf_node.name
        self.nf_class = nf_node.nf_class
        self.setup_node_nf_type()
        self.service_path_id = nf_node.service_path_id
        self.service_id = nf_node.service_id
        self.transition_condition = copy.deepcopy(nf_node.transition_condition)
        self.argument = copy.deepcopy(nf_node.argument)
        return

    def update_shared_module(self, nf_node):
        """
        Description: this function updates the spi/si values for a shared NF module.
        """
        if (nf_node.service_path_id, nf_node.service_id) not in self.shared_spi_list:
            self.shared_spi_list.append((nf_node.service_path_id, nf_node.service_id))
        return

    def setup_node_nf_type(self):
        """
        Description:
        This function will return:
        -1, if the module is invalid;
        0, if the module is a P4 module;
        1, if the module is a BESS module;
        2, if the module can be either a P4 module or a BESS module;
        """
        global bess_module_list
        global p4_module_list, p4_14_module_list
        bess_node, p4_node = 0, 0
        if self.nf_class in bess_module_list:
            bess_node = 1
        if (self.nf_class in p4_module_list) or (self.nf_class in p4_14_module_list):
            p4_node = 1
        self.nf_type = -1+ bess_node* 2 + p4_node
        return

    def bind_node_nf_type(self, nf_node_type):
        self.nf_type = nf_node_type
        return

    def is_entry(self):
        return (self.entry_flag)

    def is_dummy_node(self):
        return (self.nf_class=="EmptyChain")

    def is_p4(self):
        return (self.nf_type==0 or self.nf_type==2)

    def is_nshencap(self):
        nshencap_name = 'nsh_%d_%d' %(self.service_path_id, self.service_id)
        return (nshencap_name==self.name)

    def is_dup_avoid(self):
        global dup_avoid_list
        return self.nf_class in dup_avoid_list

    def is_shared_module(self):
        return (len(self.shared_spi_list)!=0)

    def is_bess(self):
        return (self.nf_type==1 or self.nf_type==2)

    def is_both(self):
        return self.nf_type==2

    def is_branched_out(self):
        return (len(self.branch_str)>0)

    def is_branch_node(self):
        return (len(self.adj_nodes)>1)

    def not_end_of_chain(self):
        return (len(self.adj_nodes)>0)

    def is_merge(self):
        return (self.parent_count>1)

    def add_neighbor(self, neighbor_nf_node):
        if neighbor_nf_node not in self.adj_nodes:
            self.adj_nodes.append(neighbor_nf_node)
            neighbor_nf_node.prev_nodes.append(self)
        return

    def __cmp__(self, other_nf_node):
        if self.name < other_nf_node.name:
            return -1
        elif self.name > other_nf_node.name:
            return 1
        else:
            if self.service_path_id < other_nf_node.service_path_id:
                return -1
            elif self.service_path_id == other_nf_node.service_path_id:
                if self.service_id < other_nf_node.service_id:
                    return -1
                elif self.service_id == other_nf_node.service_id:
                    return 0
                else:
                    return 1
            else:
                return 1

    def __str__(self):
        res_str = "%s(%s)[spi=%d,si=%d,type=%d] Trans:%s Args:%s" %(self.nf_class, self.name, self.service_path_id, self.service_id, self.nf_type, str(self.transition_condition), str(self.argument))
        return res_str

    def get_nf_node_list(self):
        """
        get_nf_node_list:
        This function returns a list of nf_node. The list includes all nodes in 
        the branch, starting from the current nf_node.
        """
        res_nf_nodes = []
        res_nf_nodes.append(self)
        for tmp_node in self.adj_nodes:
            res_nf_nodes += tmp_node.get_nf_node_list()
        return res_nf_nodes

    def nf_node_store_macro(self, input_macro_list):
        self.macro_list = copy.deepcopy(input_macro_list)
        return

    def nf_node_store_const(self, input_const_list):
        self.const_list = copy.deepcopy(input_const_list)
        return

    def nf_node_store_header(self, input_header_list):
        """
        This function will store all headers in the list named self.headers
        """
        self.header_list = copy.deepcopy(input_header_list)
        return

    def nf_node_store_metadata(self, input_header_dict):
        """
        This function will store all headers in the list named self.headers
        """
        self.metadata_dict = copy.deepcopy(input_header_dict)
        return

    def nf_node_store_parser_state(self, input_state_list):
        """
        This function will store all parser states in the list named self.parser_states
        """
        self.parser_state_list = copy.deepcopy(input_state_list)
        return

    def nf_node_store_ingress_code(self, default_prefix, field_list, field_list_calc, actions, tables, apply_rules):
        """
        This function will store actions, tables, apply rules in the OrderedDict()
        Also, default_prefix is stored as self.output_prefix
        """
        self.output_prefix = copy.deepcopy(default_prefix)
        self.field_lists = copy.deepcopy(field_list)
        self.field_list_calcs = copy.deepcopy(field_list_calc)
        self.action_prefix = copy.deepcopy(default_prefix)
        self.table_prefix = self.action_prefix + "_%d_%d" %(self.service_path_id, self.service_id)
        self.ingress_actions = copy.deepcopy(actions)
        self.ingress_tables = copy.deepcopy(tables)
        self.ingress_apply_rule = copy.deepcopy(apply_rules)
        return

    def nf_node_store_egress_code(self):
        return

    def nf_node_store_deparser(self, input_header_list):
        self.deparser_header_list = copy.deepcopy(input_header_list)
        return

    def nf_node_store_arg(self, input_arg_list):
        self.arg = input_arg_list
        return
    
    def nf_node_store_nickname(self, nickname):
        self.nickname = nickname
        return

    def nf_node_set_bounce(self):
        self.bounce = True
        return

    def nf_node_set_branch_str(self, branch_str):
        self.branch_str = branch_str
        return

    def reset_mark(self):
        self.reset = True
        return


def nfcp_nf_chain_length(p4_list):
    """
    nfcp_nf_chain_length(...):
    The function returns the length of each NF service chain in terms of the
    # of P4 nodes.
    Input: p4_list (type=list)
    Output: length (type=int)
    """
    nf_chain_length = []
    for node in p4_list:
        if node.service_path_id > len(nf_chain_length):
            nf_chain_length.append(node.service_id)
        else:
            len_n = len(nf_chain_length)
            if node.service_id > nf_chain_length[len_n-1]:
                nf_chain_length[len_n-1] = node.service_id
    return nf_chain_length


def nfcp_get_bess_module_name(module_name):
    """
    nfcp_get_bess_module_name:
    The function removes the brackets and returns the BESS NF's name
    """
    res = re.match(r"(.*)\((.*)\)", module_name, re.M|re.I)
    return bess_module




