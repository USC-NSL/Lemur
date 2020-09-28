"""
* 
* TEST_USER_LEVEL_PARSER.PY - 
* This script is used to test nfcp_user_level_parser.py
* 
* Author: Jianfeng Wang
* Time: 07-09-2017
* Email: jianfenw@usc.edu
*
"""

import sys
import os
import subprocess
import collections
import copy
import unittest
from util.nfcp_nf_node import *
from util.lang_parser_helper import *
from antlr4 import *
from NFCPUserLexer import NFCPUserLexer
from NFCPUserParser import NFCPUserParser
from NFCPUserListener import NFCPUserListener
from UDNFCPUserListener import UDNFCPUserListener, linkedlist_node



this_dir = os.path.dirname(os.path.realpath(__file__))
script_dir = os.path.join(this_dir, 'conf')


class TestUserLevelParser(unittest.TestCase):

	def test_draw_pipeline(self):
		pass



if __name__ == '__main__':
	unittest.main()
