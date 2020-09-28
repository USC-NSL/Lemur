
"""
* Title: nfcp_utils.py
* Description:
* This file provides common helper functions for the whole system.
* 
* Author: Jianfeng Wang
* Time: 02/26/2018
* Email: jianfenw@usc.edu
*
"""


def lib_combiner_merge_list(input_all_lists):
	"""
	Goal: Generate a final list, so that every elements in the res_list contains
	the following feature.
	For a, b in res_list (where idx(a) < idx(b)), if a, b exist in a input_list 
	then in the specific list, idx(a) < idx(b) still holds.
	Input: input_all_lists (type=list)
	Output: res_list (type=list)
	"""
	res_list = []
	for curr_list in input_all_lists: # merge a single list
		curr_pos = 0
		for curr_head in curr_list:
			if curr_head not in res_list:
				res_list.insert(curr_pos, curr_head)
				curr_pos += 1
			else:
				curr_pos = res_list.index(curr_head)
	return res_list




