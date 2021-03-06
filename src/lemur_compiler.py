"""
* This script has the main function of Lemur compiler. Lemur compiler
* parses user-defined NF chains and profiling inputs, and runs an
* optimizer that decides the placement of each NF across available
* hardware platforms. Finally, it generates code and scripts to run NFs.
*
* It will:
* (1) call "lemur_user_level_parser"
* Goal: analyze an user-input config file.
* It parses the file and stores NF-chain info in data structs that can be
* used in the rest components.
*
* (2) call "library_parser_naive"
* Goal: analyze each P4 NF node.
* It parses all P4 modules, and stores module information as NF nodes in
* nf_node objects.
*
* (3) call "library_combiner" or similar things
* Goal: merge all P4 libraries together. 
* It generates the code that unifies NF chains deployed at each hardware
* platform (P4, BESS, smartNICs and so on).
*
* (4) call "p4/bess_code_generator" 
* They generate the final code and scripts
"""

from __future__ import print_function
import os
import subprocess
import collections
import argparse
import logging
import lemur_user_level_parser as configParser
import lemur_p4lib_parser as libParser
import lemur_code_generator as codeGenerator
import util.lang_parser_helper as lang_helper
import lemur_bess_generator as BG
import time
from util.lemur_nf_node import *
from core.lemur_p4_profiler import p4_usage_checker
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
    This function generates a argument parser for Lemur compiler.
    Lemur compiler runs in different modes.
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
    parser.add_argument(
        '--pisa',
        action='store_true',
        help='enable p4 stage compilation check'
    )
    return parser


def lemur_compiler_main():
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

    entry_filename = input_filename
    p4_code_name = "nf"
    final_p4_filename = os.path.join(OUTPUT_DIR, p4_code_name.strip() + ".p4")
    final_bess_filename = os.path.join(OUTPUT_DIR, p4_code_name.strip() + ".bess")
    output_fp = open(final_p4_filename, 'w')
    output_fp.write("\n")

    # Lemur compiler runs the user-level parser to read in NF chains.
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

    # Global view of NF DAGs
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
    BG.generate_bess(conf_parser, all_nodes)

    # Use 'nfcp_library_parser' to parse each P4 library
    print("NFCP Lib Parser is running...")
    for p4_node in p4_list:
        lib_filename = p4_14_module_list[p4_node.nf_class]
        if p4_version == 'p414':
            lib_dir = os.path.join(P414_LIB_DIR, lib_filename)
        elif p4_version == 'p416':
            lib_dir = os.path.join(P416_LIB_DIR, lib_filename)

        p4_logger.info("Read '%s': processing '%s'[spi=%d,si=%d]" %(lib_filename, p4_node.name, \
            p4_node.service_path_id, p4_node.service_id))

        lib_parser = libParser.lemur_p4lib_parser(lib_dir, p4_node)

        p4_logger.info("lib info: %d macros, %d const variables" %(len(p4_node.macro_list), len(p4_node.const_list)))
        p4_logger.info("lib info: headers: %s" %(str(p4_node.header_list)))
        p4_logger.info("lib info: %d metadata fields" %(len(p4_node.metadata_dict)))
        p4_logger.info("lib info: %d parser states" %(len(p4_node.parser_state_list)))
        p4_logger.info("lib info: prefix=%s, %d actions, %d tables" %(p4_node.output_prefix, len(p4_node.ingress_actions), len(p4_node.ingress_tables)))

    p4_generator = codeGenerator.lemur_code_generator(conf_parser.scanner, p4_list, p4_version)

    print("NFCP P4 Library Combiner is running...")
    p4_generator.lib_combine_main()
    p4_generator.lib_combine_show_stats(p4_logger)

    print("NFCP P4 Code Generator is running...")
    output_fp.write(p4_generator.code_generator_main())
    
    output_fp.close()
    print("NFCP Compiler Ends!")

    """
    # If you have a P4 switch and configure it in connect.py, you can
    # use the P4 stage estimator to verify the generated P4 code can
    # fit in the target hardware.
    # P4 stage estimator code example:
    checker = p4_usage_checker( './nf.p4', p4_list, 12 )
    cker_res = checker.lemur_check_p4_stage_usage()
    print('NFCP switch estimation:', checker.stage_usage, 'estimation res:', cker_res)
    """
    return


if __name__ == "__main__":
    lemur_compiler_main()
