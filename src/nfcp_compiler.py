
"""
* Title: nfcp_compiler.py
* Description:
* The script is used to process a NFCP user-level configuration script and generate the corresponding P4 code.
* It will:
* (1) call "nfcp_chain_parser" / "nfcp_user_level_parser"
* Goal: analyze the user-input configuration file. 
* Generate data structs that are useful when generating P4 and BESS code.
*
* (2) call "library_parser_naive" or similar things
* Goal: analyze each P4 NF node. Store the necessary information in the NF node data structure
*
* (3) call "library_combiner" or similar things
* Goal: merge all P4 libraries together. Generate the glue code to make the NF chain running
* 
* (4) call "p4_code_generator" 
* Goal: generate P4 code and output it
*
"""

from __future__ import print_function
import os
import subprocess
import collections
import argparse
import logging
import nfcp_user_level_parser as configParser
import nfcp_library_parser as libParser
import nfcp_code_generator as codeGenerator
import nfcp_bess_generator as bessGenerator
import util.lang_parser_helper as lang_helper
import new_bess_generator as BG
import time
from util.lemur_nf_node import *
from util.nfcp_install_table_entry import NFCP_entry_helper
from core.profile_p4 import p4_usage_checker
import nf_placement as placeTool
from nf_placement import log_module


'''
MAIN_PLACE_LOGGER = logging.getLogger('MAIN_PLACE_LOGGER')
MAIN_PLACE_LOGGER.setLevel(logging.DEBUG)
MAIN_FH = logging.FileHandler('main_placement.log')
MAIN_FH.setLevel(logging.DEBUG)
MAIN_FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
MAIN_FH.setFormatter(MAIN_FORMATTER)
'''

# create P4 logger
p4_logger = logging.getLogger('p4_logger')
p4_logger.setLevel(logging.DEBUG)

fp = logging.FileHandler('p4.log')
fp.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s: %(message)s')
fp.setFormatter(formatter)
p4_logger.addHandler(fp)

# set up directories for conf scripts, P4_14 libraries and P4_16 libraries
global CONF_LIB
global P414_LIB_DIR
global P416_LIB_DIR
global OUTPUT_DIR

# for topo sort, the global traverse_time
global global_traverse_time

CONF_LIB_DIR = "./user_level_examples"
P414_LIB_DIR = "./p4_14_lib/"
P416_LIB_DIR = "./p4_lib/"
OUTPUT_DIR = "./"
traverse_time = 0

def get_argparse():
    """
    Description: generate the argument parser to read command line inputs
    Input: None
    Output: argparser
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--lang', '-l', 
        nargs='*', 
        choices=['p414', 'p416'], 
        default=['p414'], 
        help='Please specify the target P4 language'
        )
    parser.add_argument(
        '--iter',
        action='store_true',
        help='start iterate after first time compilation'
    )
    parser.add_argument(
        '--file', '-f',
        help='specify configuration file name'
    )
    parser.add_argument(
        '--mode', '-m',
        type=int,
        action="store",
        choices=[0,1,2,3,4,5,6,7],
        default=0,
        help='specify mode, 0: core_op, 1: no_profile, 2: greedy priotize one chain by another, 3: all P4, 4: no core_op, 5: E2, 6: P4 usage estimation, 7: all BESS'
    )

    parser.add_argument(
        '--of',
        action='store_true',
        help='Replace P4 with Openflow'
    )
    return parser


def nfcp_compiler_main():
    """
    The main function for the NFCP compiler. It follows these steps:
    (1) user-level NF chain parser
    (2) library parser and process each P4 libraries
    (3) NFCP P4/BESS code generator
    """
    global bess_module_list, p4_module_list, p4_14_module_list
    global CONF_LIB, P414_LIB_DIR, P416_LIB_DIR, OUTPUT_DIR

    print("List all user-level configuration scripts:")
    subprocess.call(['ls', './user_level_examples'])

    arg_parser = get_argparse()
    args = arg_parser.parse_args()
    enumerate_bool = args.iter
    of_flag = args.of
    p4_version = args.lang[0]
    op_mode = args.mode
    input_filename = args.file

    print('input mode: %d' % op_mode)
    print("NFCP Compiler Starts:")
    print("Compiling file: %s" % input_filename)
    config_filename = './user_level_examples/'+input_filename+'.conf'
    #config_filename = './user_level_examples/'+raw_input("Please input the NF chain configuration filename: ")
    #config_filename = './user_level_examples/'+'test_sharedmods.conf'
    entry_filename = input_filename
    p4_code_name = "nf"
    final_p4_filename = os.path.join(OUTPUT_DIR, p4_code_name.strip() + ".p4")
    final_bess_filename = os.path.join(OUTPUT_DIR, p4_code_name.strip() + ".bess")
    output_fp = open(final_p4_filename, 'w')
    output_fp.write("\n")

    # NFCP Compiler New Version (Refer: nfcp_user_level_parser.py)
    # Use the 'configParser' class to parser the NF chain configuration file
    p4_logger.info('NFCP ConfParser is running...')
    conf_parser = configParser.Lemur_config_parser(config_filename)
    for flowspec_name, nfchain_name in conf_parser.scanner.flowspec_nfchain_mapping.items():
        chain_ll_node = conf_parser.scanner.struct_nlinkedlist_dict[nfchain_name]
        flowspec_instance = conf_parser.scanner.struct_nlist_dict[flowspec_name]
        p4_logger.info(" -flow[%s]: %s\n" %(flowspec_name, flowspec_instance))
        # Print all pipelines to the NFCP users
        print(chain_ll_node._draw_pipeline())
        pipeline_fp = open(('_pipeline.txt'), 'a+')
        pipeline_fp.write(chain_ll_node._draw_pipeline())
        pipeline_fp.close()
    start_time = time.time()
    all_nf_nodes = placeTool.place_decision(conf_parser, enumerate_bool, op_mode)
    print("--- %s seconds ---" % (time.time() - start_time))
    all_nodes = all_nf_nodes
    
    p4_list = []
    if all_nf_nodes:
        p4_logger.info(" -stats: total %d nodes" %(len(all_nf_nodes)))
    for idx, node in enumerate(sorted(all_nf_nodes)):
        p4_logger.info(('%s, time:%d') %(node, node.finish_time))
    conf_parser.conf_parser_show_stats(p4_logger)
    # non-global view (it does not work with shared modules)
    #p4_node_lists = conf_parser.conf_parser_get_p4_nodes(copy.deepcopy(all_nf_nodes))
    # global view
    p4_node_lists = conf_parser.conf_parser_get_global_p4_nodes(copy.deepcopy(all_nf_nodes))
    default_nsh_node = nf_node()
    default_nsh_node.setup_node_from_argument('sys_default', 'SYS', 0, 0)
    p4_node_lists.insert(0, [default_nsh_node])
    all_p4_nodes = []
    for node_list in p4_node_lists:
        # for each service path, we do topo sorting
        node_list.sort(cmp=lambda x,y:cmp(x.finish_time, y.finish_time), reverse=True)
        all_p4_nodes += node_list
    p4_list = copy.deepcopy(all_p4_nodes)

    # Open BESS script
    bess_fp = open(final_bess_filename, 'w')
    BG.generate_bess(conf_parser, all_nodes)
    '''
    writein_list = bessGenerator.convert_graph_to_bess(conf_parser, all_nodes)

    for bess_line in writein_list:
        bess_fp.write(bess_line)
        bess_fp.write('\n')
    bess_fp.close()
    '''
    
    # Use 'nfcp_library_parser' to parse each P4 library
    # Method: libParser.nfcp_lib_parser(lib_repo, nf_node)
    print("NFCP Lib Parser is running...")
    for p4_node in p4_list:
        lib_filename = p4_14_module_list[p4_node.nf_class]
        if p4_version == 'p414':
            lib_dir = os.path.join(P414_LIB_DIR, lib_filename)
        elif p4_version == 'p416':
            lib_dir = os.path.join(P416_LIB_DIR, lib_filename)

        p4_logger.info("Read '%s': processing '%s'[spi=%d,si=%d]" %(lib_filename, p4_node.name, \
            p4_node.service_path_id, p4_node.service_id))
        lib_parser = libParser.nfcp_lib_parser(lib_dir, p4_node)
        p4_logger.info("lib info: %d macros, %d const variables" %(len(p4_node.macro_list), len(p4_node.const_list)))
        p4_logger.info("lib info: headers: %s" %(str(p4_node.header_list)))
        p4_logger.info("lib info: %d metadata fields" %(len(p4_node.metadata_dict)))
        p4_logger.info("lib info: %d parser states" %(len(p4_node.parser_state_list)))
        p4_logger.info("lib info: prefix=%s, %d actions, %d tables" %(p4_node.output_prefix, len(p4_node.ingress_actions), len(p4_node.ingress_tables)))
    # return # to test P4 Library Parser
    
    p4_generator = codeGenerator.nfcp_code_generator(conf_parser.scanner, p4_list, p4_version)
    print("NFCP P4 Library Combiner is running...")
    p4_generator.lib_combine_main()
    p4_generator.lib_combine_show_stats(p4_logger)
    #return # to test P4 Library Combiner

    print("NFCP P4 Code Generator is running...")
    output_fp.write(p4_generator.code_generator_main())
    
    output_fp.close()
    print("NFCP Compiler Ends!")
    
    
    # P4 stage estimator code example:
    checker = p4_usage_checker( './nf.p4', p4_list, 12 )
    cker_res = checker.NFCP_check_p4_stage_usage()
    print('NFCP switch estimation:', checker.stage_usage, 'estimation res:', cker_res)
    
    """
    if (op_mode==0 or op_mode==6) and False: # To insert entry, set the flag to True
        # The checker tells whether the target program fits into the switch or not
        checker = p4_usage_checker( './nf.p4', p4_list, 12)
        print("check stage")
        print(checker.NFCP_check_p4_stage_usage())
    """

    # generate entry for tests
    #entry_helper = NFCP_entry_helper(entry_filename, p4_list)
    #entry_helper.NFCP_generate_table_entries()
    return


if __name__ == "__main__":
    nfcp_compiler_main()

