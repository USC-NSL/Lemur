"""
*
* This is Lemur's user-defined parser class.
* After Lemur parses the user-defined NF chains, results are stored
* as an user-defined parser class object as a Abstract Syntax Tree (AST).
* The (AST) object contains all necessary data and provides methods to
* traverse the AST.
* The class also provides additional functions that convert the AST into
* an NF DAG, which can be used by Lemur compiler.
*
"""

from __future__ import print_function
import sys
sys.path.append('..')
import subprocess
import copy
import collections
from antlr4 import *
from LemurUserParser import LemurUserParser
from LemurUserListener import LemurUserListener
from util.lemur_nf_node import nf_chain_graph, nf_node

# The global SPI and SI values
global spi_val, si_val
# The global counter for anonymous modules
global anon_count
# The global timestamp (Debug message)
global ts

spi_val = 0
si_val = 0
anon_count = 0
ts = 0

def print_ts():
    global ts
    print('time: %d' %(ts))
    ts += 1
    return

def convert_global_nf_graph(scanner):
    """
    Convert all ll_nodes into a nf_node graph. The graph may have multiple
    head nodes and tail nodes.
    :type scanner: UDLemurUserListener
    :rtype res_graph: nf_chain_graph
    """
    global ts
    res_graph = nf_chain_graph(None)
    nf_chains = sorted(scanner.flowspec_nfchain_mapping.values())
    for nfchain in nf_chains:
        nfchain_ll_node = scanner.struct_nlinkedlist_dict[nfchain]
        nfchain_graph = convert_nf_graph(nfchain_ll_node)
        for node in nfchain_graph.list_modules():
            for next_node in node.adj_nodes:
                res_graph.add_edge(node, next_node)
            # update shared module info
            if node.is_shared_module():
                cmp_node = res_graph.get_module(node.name)
                cmp_node.shared_spi_list += node.shared_spi_list

        for head in nfchain_graph.heads:
            find_global_head = False
            for global_head in res_graph.heads:
                if head.name == global_head.name:
                    find_global_head = True
            if not find_global_head:
                res_graph.heads.append( res_graph.get_module(head.name) )
    return res_graph

def convert_nf_graph(ll_node):
    """
    This function converts a ll_node graph into a nf_node graph. This is
    used for a single NF chain. To consider multiple NF chains, please
    refer to the above function, i.e. convert_global_nf_graph.
    ll_node is an abstract representation of NF. After this function, all
    ll_nodes are converted to nf_nodes.
    :type ll_node: linkedlist_node
    :rtype res_graph: nf_chain_graph
    """
    global ts
    res_graph = nf_chain_graph(ll_node.transition_condition)

    # the elem to iterate through the linked list
    curr_ll_node = ll_node
    next_ll_node = ll_node.next
    new_node_list = None
    prev_node_list = None

    if next_ll_node == None: # chain has only one ll_node
        node_c = nf_node(curr_ll_node)
        res_graph.add_module(node_c)

    while next_ll_node != None:
        # curr_ll_node and next_ll_node are non-empty node
        if len(curr_ll_node.branch) == 0 and len(next_ll_node.branch) == 0:
            # 1. curr: non-branch, next: non_branch
            node_c = nf_node(curr_ll_node)
            node_n = nf_node(next_ll_node)
            res_graph.add_edge(node_c, node_n)
        elif len(curr_ll_node.branch) == 0 and len(next_ll_node.branch) != 0:
            # 2. curr: non-branch, next: branch
            node_c = nf_node(curr_ll_node)
            res_graph.add_module(node_c)

            tmp_tail = []
            branch_idx = 0
            for curr_branch in next_ll_node.branch:
                branch_idx += 1
                # for each branch, we get the sub-graph
                curr_branch_graph = convert_nf_graph(curr_branch)
                tmp_tail += curr_branch_graph.tails
                # merge the two graphs
                for node in curr_branch_graph.list_modules():
                    # add all nodes in each subchain graph
                    for next_node in node.adj_nodes:
                        res_graph.add_edge(node, next_node)
                for head_node in curr_branch_graph.heads:
                    # We create a link from the res_graph's tail to the branch's head node
                    res_graph.add_edge(node_c, head_node)
        elif len(curr_ll_node.branch) != 0 and len(next_ll_node.branch) == 0:
            # 3. curr: branch, next: non-branch
            node_n = nf_node(next_ll_node)
            """ deal with dummy node """
            for tail_node in copy.deepcopy(res_graph.tails):
                if tail_node.is_dummy_node():
                    node_n.transition_condition = copy.deepcopy(tail_node.transition_condition)
                    prev_node = tail_node.prev_nodes[0]
                    # remove the link for the dummy node
                    res_graph.del_edge(prev_node, tail_node)
            for tail_node in copy.deepcopy(res_graph.tails):
                assert(not tail_node.is_dummy_node())
                res_graph.add_edge(tail_node, node_n)
        else:
            pass
        curr_ll_node = next_ll_node
        next_ll_node = next_ll_node.next

    assert(len(res_graph.module_list) == res_graph.module_num)
    return res_graph


class linkedlist_node(object):
    def __init__(self):
        # instance = str, var, nlist
        # instance_nf_class = nf's type name
        # transition_condition = nlist
        # branch = list of network service paths (root nodes of each path)
        # length = the length for the current node
        # prev = prev node
        # next = next node
        self.instance = None
        self.instance_nf_class = None
        self.spi = 0
        self.si = 0
        self.transition_condition = None
        self.argument = None
        self.branch = []
        self.length = 0
        self.prev = None
        self.next = None

    def set_node_instance(self, node_instance, scanner):
        """
        This function post-process every 'branch' node.
        It sets up the branch list, i.e. 'self.branch' to indicate whether
        the node has any branches.
        :type node_instance: linkedlist_node
        :type scanner: nfcp_config_parser
        """
        global anon_count
        if isinstance(node_instance, list):
            self.instance = copy.deepcopy(node_instance)
        elif isinstance(node_instance, tuple):
            anon_count += 1
            self.instance = "anon_%d" %(anon_count)
            self.instance_nf_class = copy.deepcopy(node_instance[0])
            self.argument = copy.deepcopy(node_instance[1])
        elif isinstance(node_instance, str): # nf instance
            if node_instance in scanner.func_dict: # nf object dict
                self.instance = copy.deepcopy(node_instance)
                self.instance_nf_class = copy.deepcopy(scanner.func_dict[node_instance][0])
                self.argument = copy.deepcopy(scanner.func_dict[node_instance][1])
            else: # nf
                anon_count += 1
                self.instance = "anon_%d" %(anon_count)
                self.instance_nf_class = node_instance
        else:
            error_msg = 'Error: syntax error'
            raise Exception(error_msg)
        self.postprocess_branches(scanner)
        return

    def set_transition_condition(self, nlist_instance):
        """
        This function sets up the transition_condition field for the ll_node.
        Please note there are two places where you have to call this function.
        (1) configure a NF chain: 'flowspec : nfchain'
        (2) encounter a branch node: in postprocess_branches()
        Input: nlist_instance (type=list)
        Output: None
        """
        #print(type(nlist_instance))
        if not isinstance(nlist_instance, list):
            raise "Error: ll_node transition condition type error"
        else:
            self.transition_condition = copy.deepcopy(nlist_instance)

    def __len__(self):
        """
        This function returns the max length of one NF DAG that starts
        from the current node, i.e. |this|.
        """
        len_count = 0
        curr_node = self
        while curr_node != None:
            len_count += self.length
            curr_node = curr_node.next
        return len_count

    def postprocess_branches(self, scanner):
        """
        This function unwraps all branch nodes.
        Note: scanner.struct_nlinkedlist_dict stores all NF-chain instances.
        Each NF chain is indexed by the instance's name.
        :type scanner: nfcp_config_parser 
        """
        if isinstance(self.instance, list): # branch node
            # (Note: self.branch has not been setup yet, i.e. len(self.branch)==0)
            curr_branch_length, max_branch_length = 0, 0
            for subchain in self.instance:
                # subchain example: {'nfchain': '', 'flowspec': [{'gate_select': '2'}]}
                # note: subchain can be NF, nlinkedlist, and var (NF instance, ll_node instance)
                if isinstance(subchain['nfchain'], str):
                    subchain_name = subchain['nfchain']
                    if subchain_name in scanner.struct_nlinkedlist_dict:
                        # subchain is a chain instance
                        self.branch.append(scanner.struct_nlinkedlist_dict[subchain_name])
                        curr_branch_length = scanner.struct_nlinkedlist_dict[subchain_name].get_length()
                    elif len(subchain_name.strip()) == 0:
                        # subchain is an empty chain
                        new_node = linkedlist_node()
                        new_node.set_node_instance('EmptyChain', scanner)
                        new_node.set_transition_condition(subchain['flowspec'])
                        self.branch.append(new_node)
                        curr_branch_length = 0
                    else:
                        # subchain is a NF instance (such as: ttl)
                        new_node = linkedlist_node()
                        new_node.set_node_instance(subchain_name, scanner)
                        new_node.set_transition_condition(subchain['flowspec'])
                        self.branch.append(new_node)
                        curr_branch_length = 1
                    #print("str", scanner.struct_nlinkedlist_dict[subchain_name])
                elif isinstance(subchain['nfchain'], linkedlist_node):
                    # subchain is a NF chain definition
                    subchain['nfchain'].set_transition_condition(subchain['flowspec'])
                    self.branch.append(subchain['nfchain'])
                    curr_branch_length = len(subchain['nfchain'])

                max_branch_length = max(max_branch_length, curr_branch_length)
        else: # normal NF node
            self.length = 1
        return

    def get_nf_node(self):
        """
        This function converts a linkedlist (starting from |this| ll_node)
        to a normal list. Consecutive NFs in a run-to-completion format
        are merged together as one final NF node.
        Note that an NF DAG is a true DAG if it contains 'branch' nodes.
        Otherwise, the final list should only contain one nf_node.
        """
        res_node_list = []
        if len(self.branch) == 0:
            # process a non-branch node
            new_node = nf_node(self)
            res_node_list.append([new_node])
        else:
            # process a branch node
            for curr_branch in self.branch:
                tmp_list = []
                curr_node = curr_branch
                while curr_node != None:
                    if len(curr_node.branch) == 0:
                        # process a non-branch node
                        new_node = nf_node(curr_node)
                        tmp_list.append(new_node)
                    else:
                        # process a branch node
                        tmp_list = curr_node.get_nf_graph_branch()
                    res_node_list.append(tmp_list)
                    curr_node = curr_node.next
        return res_node_list

    def get_nf_graph_branch(self):
        """
        Helper function:
        process the ll->graph convertion for any 'branch' nodes
        """
        return None

    def get_length(self):
        return len(self)

    def get_all_nodes(self):
        res_nodes = []
        curr_node = self
        while curr_node != None:
            if len(curr_node.branch) == 0: # process normal node
                res_nodes.append(curr_node)
            else: # process 'branch' node
                res_nodes += curr_node.get_all_nodes_branch()

            curr_node = curr_node.next
        return res_nodes

    def get_all_nodes_branch(self):
        """
        Helper function: (get_all_nodes)
        """
        res_nodes = []
        for bb in self.branch:
            curr_node = bb
            while curr_node != None:
                if len(curr_node.branch) == 0:
                    # process normal node
                    res_nodes.append(curr_node)
                else:
                    # a branch inside a branch
                    res_nodes += curr_node.get_all_nodes_branch()
                curr_node = curr_node.next
        return res_nodes

    def _draw_pipeline(self, graph_args=None):
        """
        print_pipeline:
        Print the whole pipeline.
        1. start with a linear NF chain, which does not have any branch
        2. handle the branch struct
        """
        # generate the NF placement graph (in the output format)
        if graph_args is None:
            graph_args = []

        nf_graph = convert_nf_graph(self)
        nf_graph.verify_graph()
        modules = nf_graph.list_modules()
        names = []
        node_labels = {}

        for m in modules:
            # all NF modules in the NF chain graph
            #print('NF: %s, spi: %d, si: %d' %(m.nf_class, m.service_path_id, m.service_id))
            name = m.name
            mclass = m.nf_class
            names.append(name)
            node_labels[name] = '%s\\n%s\\n' %(mclass, name)
            node_labels[name] += 'spi:%d si:%d' %(m.service_path_id, m.service_id)

        try:
            f = subprocess.Popen('graph-easy ' + ' '.join(graph_args), shell=True,\
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE )

            for name in names:
                for next_node in nf_graph.module_list[name].adj_nodes:
                    next_nf_name = next_node.name
                    print('[%s] -> [%s]' %(node_labels[name], node_labels[next_nf_name]), file=f.stdin )
            if len(names)==1:
                name = names[0]
                print('[%s]' %(node_labels[name]), file=f.stdin)

            output, error = f.communicate()
            f.wait()
            return output

        except IOError as e:
            if e.errno == errno.EPIPE:
                raise cli.CommandError('"graph-easy" program is not available')
            else:
                raise

    def __str__(self):
        res_str = ""
        if len(self.branch) != 0:
            res_str += 'NF Branch[spi=%d]' %(self.spi)
        else:
            res_str += "%s[name=%s spi=%d si=%d]" %(self.instance_nf_class, self.instance, self.spi, self.si)
        
        if self.next != None:
            res_str += " -> " + str(self.next)
        return res_str

    # The next three functions are used to assign SPI and SI values for all NFs in a NF chain ([type==linkedlist_node])
    def assign_service_index(self):
        """ This function assigns and updates spi_val and si_val. A pair of (spi_val, si_val) is used to identify each logical NFs.
        """
        global spi_val, si_val
        if len(self.branch) != 0:
            # branch node
            self.update_service_index_nextfunc()
            for subchain in self.branch:
                # each subchain is a nll_node (i.e. the root node of the subchain)
                if subchain.instance_nf_class != 'EmptyChain':
                    self.update_service_index_nextchain()
                    subchain.assign_service_index()
            # set up the spi_val and si_val for the rest of netchain
            if self.next != None:
                self.update_service_index_nextchain()
                self.next.assign_service_index()
        else:
            # normal NF node
            self.update_service_index_nextfunc()
            if self.next != None:
                self.next.assign_service_index()
        return

    def update_service_index_nextfunc(self):
        """
        This function sets (spi, si) index for an NF in the same
        run-to-completion chain. It increases si_val by 1, and then sets
        self.spi and self.si.
        """
        global spi_val, si_val
        si_val += 1
        self.spi = spi_val
        self.si = si_val
        return
        
    def update_service_index_nextchain(self):
        """
        This function resets (spi_val, si_val) index for a new
        run-to-completion chain.
        """
        global spi_val, si_val
        spi_val += 1
        si_val = 0
        return


# This class stores all information after Lemur's user-level parser
# processes the NF-chain config file.
class UDLemurUserListener(LemurUserListener):
    def __init__(self):
        # Lookup Table for basic data types
        self.var_int_dict = {}
        self.var_float_dict = {}
        self.var_string_dict = {}
        self.var_bool_dict = {}
        self.func_dict = {}

        self.struct_ntuple_dict = {}
        self.struct_nlist_dict = {}
        self.struct_nlinkedlist_dict = {}
        self.struct_graph_dict = {}

        # flowspec_nfchain_mapping stores the nfchain configuration
        # i.e. flowspec : NF chain
        self.flowspec_nfchain_mapping = collections.OrderedDict()

        self.service_path_count = 0
        self.line_count = 0
        return

    # Enter a parse tree produced by LemurUserParser#total.
    def enterTotal(self, ctx):
        #print("Lemur AST Walker starts:")
        pass

    # Exit a parse tree produced by LemurUserParser#total.
    def exitTotal(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#line.
    def enterLine(self, ctx):
        self.line_count += 1
        pass

    # Exit a parse tree produced by LemurUserParser#line.
    def exitLine(self, ctx):
        pass

    # Enter a parse tree produced by LemurUserParser#define_int.
    def enterDefine_int(self, ctx):
        #print(ctx.VARIABLENAME(), ctx.INT(), type(str(ctx.INT())))
        var_name = str(ctx.VARIABLENAME())
        var_value = int(str(ctx.INT()))
        self.var_int_dict[var_name] = var_value
        pass

    # Exit a parse tree produced by LemurUserParser#define_int.
    def exitDefine_int(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#define_float.
    def enterDefine_float(self, ctx):
        #print(ctx.VARIABLENAME(), ctx.FLOAT(), type(str(ctx.FLfOAT())))
        var_name = str(ctx.VARIABLENAME())
        var_value = float(str(ctx.FLOAT()))
        self.var_float_dict[var_name] = var_value
        pass

    # Exit a parse tree produced by LemurUserParser#define_float.
    def exitDefine_float(self, ctx):
        pass

    def get_string_from_ctx(self, ctx, idx=None):
        if idx == None:
            res = str(ctx.STRING())[1:-1]
        else:
            res = str(ctx.STRING(idx))[1:-1]
        return res

    # Enter a parse tree produced by LemurUserParser#define_string.
    def enterDefine_string(self, ctx):
        var_name = str(ctx.VARIABLENAME())
        var_value = self.get_string_from_ctx(ctx)
        self.var_string_dict[var_name] = var_value
        pass

    # Exit a parse tree produced by LemurUserParser#define_string.
    def exitDefine_string(self, ctx):
        pass

    def get_bool_from_ctx(self, ctx):
        res = None
        bool_value = str(ctx.BOOL())
        if bool_value == 'False':
            res = False
        elif bool_value == 'True':
            res = True
        return res

    # Enter a parse tree produced by LemurUserParser#define_bool.
    def enterDefine_bool(self, ctx):
        var_name = str(ctx.VARIABLENAME())
        var_value = self.get_bool_from_ctx(ctx)
        self.var_bool_dict[var_name] = var_value
        pass

    # Exit a parse tree produced by LemurUserParser#define_bool.
    def exitDefine_bool(self, ctx):
        pass

    def get_nf_from_ctx(self, ctx):
        # return the NF's name from the netfunction context
        nf_name = str(ctx.VARIABLENAME(0))
        nf_arg = None
        if ctx.nlist() != None:
            nf_arg = self.get_nlist_from_ctx(ctx.nlist())
        elif ctx.ntuple() != None:
            nf_arg = self.get_nlist_from_ctx(ctx.ntuple())
        elif len(ctx.VARIABLENAME()) == 2:
            nf_arg = str(ctx.VARIABLENAME(1))

        res = (nf_name, nf_arg)
        return res

    # Enter a parse tree produced by LemurUserParser#define_nfinstance.
    def enterDefine_nfinstance(self, ctx):
        # Note: each NF instance can be either a BESS or P4 module
        #print("Enter Define NetFunc")
        var_name = str(ctx.VARIABLENAME())
        var_value = self.get_nf_from_ctx(ctx.netfunction())
        self.func_dict[var_name] = var_value
        pass

    # Exit a parse tree produced by LemurUserParser#define_nfinstance.
    def exitDefine_nfinstance(self, ctx):
        pass


    def get_nlistelem_from_ctx(self, nlist_elem_ctx):
        """
        return the nlist element based on the nlist_elem object's context
        """
        nlistelem_obj = nlist_elem_ctx
        res_value = None
        if nlistelem_obj.ntuple() != None:
            res_value = self.get_ntuple_from_ctx(nlistelem_obj.ntuple())
            #print("nlist elem(ntuple):", res_value)
        elif nlistelem_obj.INT() != None:
            res_value = int(str(nlistelem_obj.INT()))
        elif nlistelem_obj.FLOAT() != None:
            res_value = float(str(nlistelem_obj.FLOAT()))
        elif nlistelem_obj.STRING() != None:
            res_value = self.get_string_from_ctx(nlistelem_obj)
        elif nlistelem_obj.VARIABLENAME() != None:
            res_value = str(nlistelem_obj.VARIABLENAME())

        return res_value


    def get_nlist_from_ctx(self, nlist_obj):
        res_nlist = []
        nlistelem_obj_list = nlist_obj.nlist_elem()
        for nlistelem_obj in nlistelem_obj_list:
            var_value = self.get_nlistelem_from_ctx(nlistelem_obj)
            if var_value:
                res_nlist.append(var_value)
        return res_nlist

    # Enter a parse tree produced by LemurUserParser#define_nlist.
    def enterDefine_nlist(self, ctx):
        var_name = str(ctx.VARIABLENAME())
        nlist_obj = ctx.nlist()
        nlist = self.get_nlist_from_ctx(nlist_obj)
        self.struct_nlist_dict[var_name] = nlist
        pass

    # Exit a parse tree produced by LemurUserParser#define_nlist.
    def exitDefine_nlist(self, ctx):
        pass


    def get_ntupleelem_from_ctx(self, ntuple_elem_ctx):
        """
        return the ntuple element based on the ntuple_elem object's context
        Note: ntuple elem: {str : str/int/float/var/nlist/nlinkedlist}
        """
        ntupleelem_obj = ntuple_elem_ctx
        res_value = None
        if ntupleelem_obj.STRING(1) != None:
            #print( str(ntupleelem_obj.STRING(1)) )
            res_value = self.get_string_from_ctx(ntupleelem_obj, 1)
        elif ntupleelem_obj.INT() != None:
            #print( int(str(ntupleelem_obj.INT())) )
            res_value = int(str(ntupleelem_obj.INT()))
        elif ntupleelem_obj.FLOAT() != None:
            #print( float(str(ntupleelem_obj.INT())) )
            res_value = float(str(ntupleelem_obj.INT()))
        elif ntupleelem_obj.VARIABLENAME() != None:
            #print( str(ntupleelem_obj.VARIABLENAME()) )
            res_value = str(ntupleelem_obj.VARIABLENAME())
        elif ntupleelem_obj.nlist() != None:
            #print("focus", self.get_nlist_from_ctx(ntupleelem_obj.nlist()) )
            res_value = self.get_nlist_from_ctx(ntupleelem_obj.nlist())
        elif ntupleelem_obj.nlinkedlist() != None:
            res_value = self.get_nlinkedlist_from_ctx(ntupleelem_obj.nlinkedlist())
        return res_value

    def get_ntuple_from_ctx(self, ntuple_obj):
        # Note: each ntuple_elem has at most two string elements.
        res_ntuple = {}
        ntupleelem_obj_list = ntuple_obj.ntuple_elem()
        for ntupleelem_obj in ntupleelem_obj_list:
            #print( str(ntupleelem_obj.STRING(0)) )
            var_name = self.get_string_from_ctx(ntupleelem_obj, 0)
            var_value = self.get_ntupleelem_from_ctx(ntupleelem_obj)
            res_ntuple[var_name] = var_value
        return res_ntuple

    # Enter a parse tree produced by LemurUserParser#define_ntuple.
    def enterDefine_ntuple(self, ctx):
        #print("Enter Define Tuple")
        var_name = str(ctx.VARIABLENAME())
        ntuple_obj = ctx.ntuple()
        ntuple = self.get_ntuple_from_ctx(ntuple_obj)
        self.struct_ntuple_dict[var_name] = ntuple
        pass

    # Exit a parse tree produced by LemurUserParser#define_ntuple.
    def exitDefine_ntuple(self, ctx):
        pass


    def get_nlinkedlistelem_from_ctx(self, nll_elem_obj):
        # Note: nlinkedlistelem can be netfunc (str), var (str), nlist (list)
        res_value = None
        if nll_elem_obj.netfunction() != None:
            #print('nll elem - netfunc:', str(nll_elem_obj.netfunction().VARIABLENAME()))
            res_value = self.get_nf_from_ctx(nll_elem_obj.netfunction())
        elif nll_elem_obj.VARIABLENAME() != None:
            #print('nll elem - var:', str(nll_elem_obj.VARIABLENAME()))
            res_value = str(nll_elem_obj.VARIABLENAME())
        elif nll_elem_obj.nlist() != None: # a 'branch' node
            #print('nll elem - nlist:', self.get_nlist_from_ctx(nll_elem_obj.nlist()))
            res_value = self.get_nlist_from_ctx(nll_elem_obj.nlist())
        return res_value

    def get_nlinkedlist_from_ctx(self, nlinkedlist_obj):
        """
        This function will return the root node for the defined linkedlist.
        At this point, we don't have to further process the linkedlist.
        Input: ll_node_ctx
        Output: root_node (type=ll_node)
        """
        root_ll_node = None
        curr_ll_node = root_ll_node
        nll_obj_list = nlinkedlist_obj.nlinkedlist_elem()
        for nll_elem_obj in nll_obj_list:
            # for each ll_elem, we create a ll_node instance
            # ll_node.instance : nlist / Var / NF(with args) (before postprocessing)
            new_ll_node = linkedlist_node()
            node_instance = self.get_nlinkedlistelem_from_ctx(nll_elem_obj)
            new_ll_node.set_node_instance(node_instance, self)
            if root_ll_node == None: # set up the root node
                new_ll_node.prev = None
                root_ll_node = new_ll_node
            else: # set up the curr_ll_node's next node
                new_ll_node.prev = curr_ll_node
                curr_ll_node.next = new_ll_node
            curr_ll_node = new_ll_node
        return root_ll_node

    # Enter a parse tree produced by LemurUserParser#define_nlinkedlist.
    def enterDefine_nlinkedlist(self, ctx):
        """
        Enter a new NF chain definition (a nlinkedlist)
        Update the SPI and SI values:
        SPI += 1, SI = 0
        """
        print("Enter Define nLinkedList")
        var_name = str(ctx.VARIABLENAME())
        nlinkedlist_obj = ctx.nlinkedlist()
        nlinkedlist = self.get_nlinkedlist_from_ctx(nlinkedlist_obj)
        #print("Store nlinkedlist[name=\"%s\", len=%d]" %(var_name, len(nlinkedlist)))
        self.struct_nlinkedlist_dict[var_name] = nlinkedlist
        return

    # Exit a parse tree produced by LemurUserParser#define_nlinkedlist.
    def exitDefine_nlinkedlist(self, ctx):
        pass

    # Enter a parse tree produced by LemurUserParser#define_flowspec.
    def enterDefine_flowspec(self, ctx):
        var_name = str(ctx.VARIABLENAME())
        flowspec_obj = ctx.flowspec()
        nlist_obj = flowspec_obj.nlist()
        nlist = self.get_nlist_from_ctx(nlist_obj)
        self.struct_nlist_dict[var_name] = nlist
        return

    # Exit a parse tree produced by LemurUserParser#define_flowspec.
    def exitDefine_flowspec(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#define_nfchain.
    def enterDefine_nfchain(self, ctx):
        var_name = str(ctx.VARIABLENAME())
        #print("Enter Define nfchain %s" %(var_name))
        netfunc_chain_obj = ctx.netfunction_chain()
        nlinkedlist_obj = netfunc_chain_obj.nlinkedlist()
        nlinkedlist = self.get_nlinkedlist_from_ctx(nlinkedlist_obj)
        #print("Store nlinkedlist[name=\"%s\", len=%d]" %(var_name, len(nlinkedlist)))
        self.struct_nlinkedlist_dict[var_name] = nlinkedlist
        return

    # Exit a parse tree produced by LemurUserParser#define_nfchain.
    def exitDefine_nfchain(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#configue_nfchain.
    def enterConfig_nfchain(self, ctx):
        # When a NF chain is configured with a flowspec, we then consider
        # the placement of the NF chain (starting by assigning SPI and SI
        # values for each NF)
        global spi_val, si_val
        spi_val += 1
        si_val = 0

        self.service_path_count += 1
        flowspec = str(ctx.VARIABLENAME(0))
        flowspec_instance = self.struct_nlist_dict[flowspec]
        nfchain = str(ctx.VARIABLENAME(1))
        nfchain_instance = self.struct_nlinkedlist_dict[nfchain]
        nfchain_instance.assign_service_index()
        nfchain_instance.set_transition_condition(flowspec_instance)
        self.flowspec_nfchain_mapping[flowspec] = nfchain
        #print("Configure chain[%s]: %s" %(nfchain, str(nfchain_instance)))
        return

    # Exit a parse tree produced by LemurUserParser#configue_nfchain.
    def exitConfig_nfchain(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#flowspec.
    def enterFlowspec(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#flowspec.
    def exitFlowspec(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#netfunction_chain.
    def enterNetfunction_chain(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#netfunction_chain.
    def exitNetfunction_chain(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#netfunction.
    def enterNetfunction(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#netfunction.
    def exitNetfunction(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#nlist.
    def enterNlist(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#nlist.
    def exitNlist(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#nlist_elem.
    def enterNlist_elem(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#nlist_elem.
    def exitNlist_elem(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#ntuple.
    def enterNtuple(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#ntuple.
    def exitNtuple(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#ntuple_elem.
    def enterNtuple_elem(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#ntuple_elem.
    def exitNtuple_elem(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#nlinkedlist.
    def enterNlinkedlist(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#nlinkedlist.
    def exitNlinkedlist(self, ctx):
        pass


    # Enter a parse tree produced by LemurUserParser#nlinkedlist_elem.
    def enterNlinkedlist_elem(self, ctx):
        pass

    # Exit a parse tree produced by LemurUserParser#nlinkedlist_elem.
    def exitNlinkedlist_elem(self, ctx):
        pass







