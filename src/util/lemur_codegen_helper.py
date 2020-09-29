"""
* This file includes helper functions used in Lemur's P4 code generator.
"""

def lib_combiner_merge_list(input_all_lists):
	""" Unify deparser lists.
	Input lists container many duplicative elements. Given many deparser
	lists, this function outputs a final list, so that every elements
	follow this rule:
	For any pairs of a and b in the res_list, if (1) a, b exist in one
	of the input list, (2) index(a) < index(b) in the input list, then
	idx(a) < idx(b) still holds in the final list.

	Input: input_all_lists (type=list)
	Output: res_list (type=list)
	"""
	res_list = []
	for curr_list in input_all_lists:
		curr_pos = 0
		for curr_head in curr_list:
			if curr_head not in res_list:
				res_list.insert(curr_pos, curr_head)
				curr_pos += 1
			else:
				# if curr_head is found, then the next pos should at
				# least be index(curr_head) + 1.
				curr_pos = res_list.index(curr_head) + 1
	return res_list


if __name__ == '__main__':
	test_list_1 = [1, 2, 3, 4]
	test_list_2 = [3, 5]
	print lib_combiner_merge_list([test_list_1, test_list_2])
