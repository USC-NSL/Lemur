"""
* This script implements Lemur's P4 module parser class.
* The P4 module parser extracts critical module information from a P4
* NF implementation.
* Typically, it extracts necessary headers, the header parser and
* deparser, and match/action tables and ingress/egress logic of
* composing a P4 pipeline.
"""

from __future__ import print_function
import os
import subprocess
import collections
import copy
import p4_lib_parser.header as header
import p4_lib_parser.my_parser as MyParser
import p4_lib_parser.ingress_match_action as MyIngress
import p4_lib_parser.egress_match_action as MyEgress
import p4_lib_parser.my_deparser as MyDeparser
import util.lang_parser_helper as lang_helper
from util.lemur_nf_node import *


class lemur_p4lib_parser(object):
    """ P4 NF module parser
    The parser reads in a P4 NF module (under p4_14_lib). Given a P4 NF
    module and a NF node object, the parser extracts and stores critical
    module info in the NF node object.

    lemur_code_generator is built on top of this class, and further
    generates the final P4 code for a P4 pipeline.
    Args:
        lib_filename: the target P4 module file (type=str)
        nf_node: the NF node that stores critical module information
        (note: this class does not create its own NF node. Instead,
        it reuses NF node objects passed by Lemur compiler.)
    """
    def __init__(self, lib_filename, nf_node):
        self.lib_filename = None
        self.nf_node = nf_node

        if lib_filename != None:
            self.lib_filename = copy.deepcopy(lib_filename)
            self.lib_parser_main()

    def lib_parser_main(self):
        """ This function is the main function of parsing a P4 module.
        It reads in all necessary fields one by one.
        """
        self.lib_parser_handle_const_var()
        self.lib_parser_handle_header()
        self.lib_parser_handle_metadata()
        self.lib_parser_handle_parser_state()
        self.lib_parser_handle_ingress()
        self.lib_parser_handle_deparser_state()

    def lib_parser_handle_const_var(self):
        cp = header.const_var_parser()
        cp.read_macros(self.lib_filename)
        self.nf_node.nf_node_store_macro(cp.macro_list)

        cp.read_const_variables(self.lib_filename)
        self.nf_node.nf_node_store_const(cp.const_list)
        return

    def lib_parser_handle_header(self):
        hp = header.header_parser([], collections.OrderedDict())
        hp.read_headers(self.lib_filename)
        self.nf_node.nf_node_store_header(hp.headers)
        return

    def lib_parser_handle_metadata(self):
        hp = header.header_parser([], collections.OrderedDict())
        hp.read_metadata(self.lib_filename)
        self.nf_node.nf_node_store_metadata(hp.metadata)
        return

    def lib_parser_handle_parser_state(self):
        """ This function parses the header parser tree of a P4 module.
        Note: the header parser is a tree structure, where each node
        represents a common header and may have many transitional edges
        to other headers.
        """
        mpp = MyParser.myparser()
        mpp.read_transition_rules(self.lib_filename)

        for state in mpp.state_list:
            if state.branch_num != len(state.transition_info):
                print("Error:", state.name, state.branch_num, state.transition_info)
        self.nf_node.nf_node_store_parser_state(mpp.state_list)
        return

    def lib_parser_handle_ingress(self):
        """ This function parses the ingress section of a P4 module.
        Each module has a unique string as the action and table's prefix.
        This function parses actions, tables, and the logic of applying tables.
        """
        ingress = MyIngress.ingress_match_action()
        ingress.read_default_prefix(self.lib_filename)
        ingress.read_field_operations(self.lib_filename)
        ingress.read_ingress(self.lib_filename)

        self.nf_node.nf_node_store_ingress_code( ingress.output_prefix, \
            ingress.field_list_set, ingress.field_list_calc_set, \
            ingress.action_set, ingress.table_set, ingress.apply_rule )
        return

    def lib_parser_handle_deparser_state(self):
        """ The deparser defines the header sequence for a packet at egress.
        """
        mdp = MyDeparser.mydeparser()
        mdp.read_deparser_rules( self.lib_filename )
        self.nf_node.nf_node_store_deparser(mdp.deparser_seq)
        return


def lemur_p4lib_parser_handle_const_var(p4lib_filename, nf_node):
    cp = header.const_var_parser()
    cp.read_macros(p4lib_filename)
    nf_node.nf_node_store_macro(cp.macro_list)
    cp.read_const_variables(p4lib_filename)
    nf_node.nf_node_store_const(cp.const_list)
    return

def lemur_p4lib_parser_handle_header(p4lib_filename, nf_node):
    hp = header.header_parser([], collections.OrderedDict())
    hp.read_headers(p4lib_filename)
    nf_node.nf_node_store_header(hp.headers)
    return

def lemur_p4lib_parser_handle_metadata(p4lib_filename, nf_node):
    hp = header.header_parser([], collections.OrderedDict())
    hp.read_metadata(p4lib_filename)
    nf_node.nf_node_store_metadata(hp.metadata)
    return

def lemur_p4lib_parser_handle_parser_state(p4lib_filename, nf_node):
    mpp = MyParser.myparser()
    mpp.read_transition_rules(p4lib_filename)
    for state in mpp.state_list:
        if state.branch_num != len(state.transition_info):
            error_msg = "Error: %s has a wrong branch num %d" %(state.name, state.branch_num)
            raise Exception(error_msg)
    nf_node.nf_node_store_parser_state(mpp.state_list)
    return

def lemur_p4lib_parser_handle_deparser_state(p4lib_filename, nf_node):
    mdp = MyDeparser.mydeparser()
    mdp.read_deparser_rules( p4lib_filename )
    nf_node.nf_node_store_deparser(mdp.deparser_seq)
    return

def lemur_p4lib_parser_handle_ingress(p4lib_filename, nf_node):
    ingress = MyIngress.ingress_match_action()
    ingress.read_default_prefix( p4lib_filename )
    ingress.read_actions( p4lib_filename )
    ingress.read_tables( p4lib_filename )
    ingress.read_apply_rule( p4lib_filename )
    nf_node.nf_node_store_ingress_code( \
        ingress.output_prefix, ingress.action_set, \
        ingress.table_set, ingress.apply_rule )
    return


def lemur_library_parser_tester():
    print("Lemur P4 Module Parser starts:")

    # Test nf_node data structure
    exam_node_1 = nf_node()
    exam_node_1.setup_node_from_argument(None, "SilkRoad", 1, 1)
    print('name:%s class:%s spi:%d si:%d' %(exam_node_1.name, exam_node_1.nf_class, exam_node_1.service_path_id, exam_node_1.service_id))
    
    examp_p4_lib_1 = "./p4_lib/silkroad.lib"
    lemur_library_parser_handle_header(examp_p4_lib_1, exam_node_1)
    print(exam_node_1.header_list)

    exam_p4_lib_2 = "./p4_lib/acl.lib"
    exam_node_2 = nf_node()
    exam_node_2.setup_node_from_argument(None, "ACL", 1, 2)
    print('name:%s class:%s spi:%d si:%d' %(exam_node_2.name, exam_node_2.nf_class, exam_node_2.service_path_id, exam_node_2.service_id))
    lemur_library_parser_handle_header(exam_p4_lib_2, exam_node_2)
    print("Headers -", exam_node_2.header_list)

    exam_node_2 = nf_node()
    exam_node_2.setup_node_from_argument(None, "ACL", 1, 3)
    lib_parser = lemur_p4lib_parser(exam_p4_lib_2, exam_node_2)
    print("Headers -", exam_node_2.header_list)

    print("Lemur Single Library Parser ends")
    return

if __name__ == "__main__":
    lemur_library_parser_tester()
