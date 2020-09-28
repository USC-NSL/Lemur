
#include "dedup.h"
#include "../utils/ether.h"
#include "../utils/ip.h"
#include "../utils/tcp.h"
#include "../utils/udp.h"

const Commands DEDUP::cmds = {
	{"clear", "EmptyArg", MODULE_CMD_FUNC(&DEDUP::CommandClear),
		Command::THREAD_UNSAFE}
};

CommandResponse DEDUP::CommandClear(const bess::pb::EmptyArg &) {
	return CommandSuccess();
}

CommandResponse DEDUP::Init(const bess::pb::DEDUPArg &arg[[maybe_unused]]) {
	packet_id = (long)0;
	payloadT = (long)Payload_STORE_SIZE;
	maxID = (long)MAX_PKT_ID;
	// allocate and initialize the payload store
	payload_store = (payload_t*)malloc(sizeof(payload_t) * payloadT);
	payload_t* pay_ptr = NULL;
	for (int i = 0; i < payloadT; i++) {
		pay_ptr = payload_store + i;
		//pay_ptr->ptr = NULL;
		pay_ptr->ptr = (char*)malloc(sizeof(char) * MAX_PKT_SIZE);
		pay_ptr->psize = 0;
	}
	batch_cnt = 1;
	return CommandSuccess();
}

void DEDUP::ProcessBatch(Context *ctx, bess::PacketBatch *batch) {
	using bess::utils::Ethernet;
	using bess::utils::Ipv4;
	using bess::utils::Udp;
	using bess::utils::Tcp;
	//size_t = 64-bit unsigned data type, uint8_t = 1 byte data type
	tmp_timer1 = 0;
	tmp_timer2 = 0;
	timer1 = 0;
	timer2 = 0;
	timer3 = 0;
	dt1 = 0;
	dt2 = 0;
	int cnt = batch->cnt();
	for (int i = 0; i < cnt; i++) {
		trim_flag = false;
		bess::Packet *snbuf_ptr = batch->pkts()[i];
		Ethernet *eth = snbuf_ptr->head_data<Ethernet *>();
		Ipv4 *ip = reinterpret_cast<Ipv4 *>(eth + 1);
		if ((ip->protocol != Ipv4::Proto::kUdp) && (ip->protocol != Ipv4::Proto::kTcp)) {
			continue;
		}
		// ip->header_length (1 word = 4 bytes)
		size_t ip_bytes = ip->header_length << 2;
		Udp *udp = reinterpret_cast<Udp *>(reinterpret_cast<uint8_t *>(ip) + ip_bytes);
		udp->src_port = be16_t(1000);
		size_t hdr_length = sizeof(*eth) + sizeof(*ip) + sizeof(*udp);
		char* payload = reinterpret_cast<char*>(udp + 1);
		int payload_size = snbuf_ptr->data_len() - hdr_length;

		process_packet(payload, payload_size);
		
		// trim the packet if we can compress it
		if (trim_flag) {
			//char shim_buf[] = "aaaaaaaa00000000";
			memcpy(shim_buf, INIT_SHIM, 16);
			char* shim_pos = payload + max_shim_region.org_left;
			char* resp_pos = payload + max_shim_region.org_right + 1;
			int resp_len = payload_size - 1 - max_shim_region.right;
			int tp_len = payload_size - (max_shim_region.right - max_shim_region.left + 1);
			encode_helper(shim_buf+8, max_shim_region.pid, 4);
			encode_helper(shim_buf+12, max_shim_region.left, 2);
			encode_helper(shim_buf+14, max_shim_region.right, 2);
			//LOG(INFO) << shim_buf << std::endl;
			
			bess::utils::Copy(shim_pos, shim_buf, 16, true);
			bess::utils::Copy(shim_pos+16, resp_pos, resp_len, true);
			snbuf_ptr->set_data_len(hdr_length + tp_len + 16);
			snbuf_ptr->set_total_len(hdr_length + tp_len + 16);
		}
	}

	//tt_timer1 = (tmp_timer1 + tt_timer1*(batch_cnt-1)) / batch_cnt;
	//tt_timer2 = (tmp_timer2 + tt_timer2*(batch_cnt-1)) / batch_cnt;
	//LOG(INFO) << tmp_timer1 << " " << tmp_timer2 << std::endl;
	//LOG(INFO) << "bessd DEDUP: batch size: "<< cnt << "; total t1: " << tt_timer1 << "; total t2: " << tt_timer2 << std::endl;
	//LOG(INFO) << "Init: " << timer1 << "; Comp: " << timer2 << "; Insert: " << timer3 << std::endl;
	//LOG(INFO) << "Hash+Match: " << dt1 << "; Match: " << dt2 << std::endl;
	//batch_cnt += 1;
	RunNextModule(ctx, batch);
}
void DEDUP::encode_helper(char* spos, int target_num, int bit_len) {
	/* The function writes the target number into the spos within the given bit_len.
	*/
	int bit_idx = 0;
	int curr = target_num;
	while (bit_idx < bit_len) {
		*(spos+bit_idx) = curr % 256;
		curr /= 256;
		bit_idx += 1;
	}
}
int DEDUP::process_packet(char* pkt_ptr, int payload_size) {
	/*
	// Profiling code
	long start, end;
	start = get_time();
	insert_packet(pkt_ptr, payload_size);
	end = get_time();
	tmp_timer1 += end - start;
	start = end;
	insert_fingerprint(pkt_ptr, payload_size);
	end = get_time();
	tmp_timer2 += end - start;
	// End profiling code
	*/

	insert_packet(pkt_ptr, payload_size);
	insert_fingerprint(pkt_ptr, payload_size);
	
	packet_id += 1;
	if (packet_id > maxID-1) {
		packet_id = 0;
	}
	return packet_id;
}
long DEDUP::get_time() {
	gettimeofday(&tp, NULL);
	long curr = tp.tv_sec*1000000 + tp.tv_usec;
	return curr;
}
cycles_t DEDUP::get_kcycles() {
	cycles_t res = get_cycles();
	return res;
}
long DEDUP::get_nextID() {
	return packet_id;
}
bool DEDUP::valid_ID(long target_id) {
	if (target_id - packet_id > 0) { // packet_id was in a previous round
		long convert_id = packet_id + maxID;
		if ( (convert_id - target_id >= 0) ) {
			return bool(convert_id-target_id <= payloadT-1);
		}
		else {
			return false;
		}
	}
	else {// [0, payloadT-1]
		return bool(packet_id - target_id <= payloadT - 1);
	}
}
void DEDUP::insert_packet(char* pkt_ptr, int payload_size) {
	/* insert the packet payload to the target idx 
	(Note: the code will override the previous payload)
	:type pkt_ptr: char* (the pointer of the payload)
	:type payload_size: int (the length of the packet payload)
	*/
	payload_t* payload_cell = payload_store + (packet_id % payloadT);
	/*
	if (payload_cell->ptr == NULL) {
		payload_cell->ptr = (char*)malloc(sizeof(char) * MAX_PKT_SIZE);
	}
	*/
	memcpy(payload_cell->ptr, pkt_ptr, payload_size);
	payload_cell->psize = payload_size;
}
char* DEDUP::get_payload(long target_idx) {
	char* res = NULL;
	if ((target_idx >= 0) && (target_idx <= maxID-1)) {
		res = (*(payload_store + target_idx)).ptr;
	}
	return res;
}
void DEDUP::release_payload(long target_idx) {
	payload_t* payload_cell = NULL;
	if ((target_idx >= 0) && (target_idx <= maxID-1)) {
		payload_cell = payload_store + target_idx;
		free(payload_cell->ptr);
		payload_cell->ptr = NULL;
		payload_cell->psize = 0;
	}
}
void DEDUP::insert_fingerprint(char* pkt_ptr, int payload_size) {
	/* Insert the 16 fingerprints into the fingerprint_store.
	(Note: the new finterprints will override the old ones.)
	:type pkt_ptr: char* (the pointer of the payload)
	:type payload_size: int (the length of the packet payload)
	*/
	if (payload_size <= 63+16)
		return;
	u_int64_t rabinf;
	int a[16] = {0};
	int fp_idx, idx_start, idx_end;
	std::tuple<u_int64_t, int> fp_entry;

	// Initialization: reset rolling hash class; reset max_shim_region;
	myRabin.reset();
	max_shim_region.left = 0;
	max_shim_region.right = 0;
	std::unordered_map<u_int64_t, std::pair<int, int> >::const_iterator miter;
	char* mptr;
	long mpid;
	int msize, mppos;
	// compute 16 sampled hash position
	idx_start = 63;
	idx_end = payload_size - 1;
	for(int i=0; i < 16; i++) {
		a[i] = idx_start + i * (idx_end - idx_start) / 16;
	}
	// compute the rolling hash and insert the hash values into hashmap
	fp_idx = 0;
	for(int i = 0; i < payload_size; i++) {
		rabinf = myRabin.slide8(*(pkt_ptr+i));
		if (fp_idx <= 15) {
			if (i == a[fp_idx]) {
				
				miter = fingerprint_store.find(rabinf);
				if (miter != fingerprint_store.end()) {
					mpid = (miter->second).first;
					if (!valid_ID(mpid))
						continue;
					mpid = mpid % payloadT;
					mptr = payload_store[mpid].ptr;
					msize = payload_store[mpid].psize;
					mppos = (miter->second).second;

					if ((max_shim_region.left > i-63 || max_shim_region.right < i)) {
						if (match_helper(pkt_ptr, payload_size, i-63, mptr, msize, mppos)) {
							trim_flag = true;
							max_shim_region.m_fingerprint = rabinf;
							max_shim_region.pid = mpid;
						}
					}
				}
				fingerprint_list.push_back(std::tuple<u_int64_t, int>(rabinf, i-63));
				fp_idx += 1;
			}
		}
		else {
			break; // inserted all 16 fingerprints
		}
	}

	//LOG_EVERY_N(INFO, (1 << 20)) << "Fingerprint store size: " << fingerprint_store.size() << "Fingerprint list size: " << fingerprint_list.size();
	// store the pid and the hash position in the payload
	while (fingerprint_list.size() > 0) {
		fp_entry = fingerprint_list.back();
		fingerprint_store[std::get<0>(fp_entry)] = std::make_pair(packet_id, std::get<1>(fp_entry));
		//fingerprint_store[std::get<0>(fp_entry)] = std::make_pair(0, std::get<1>(fp_entry));
		fingerprint_list.pop_back();
	}
}
bool DEDUP::match_helper(char* org, int org_len, int org_pos, char* target, int t_len, int t_pos){
	/* This function checks the matching segment and updates the max_shim_region
	:type org: char* (the new string)
	:type org_len: int (the length of the new string)
	:type org_pos: int (the hash pos in the new string)
	:type target: char* (the matched string in payload store)
	:type t_len: int (the length of the string in payload store)
	:type t_pos: int (the hash pos in the matched string in payload store)
	*/

	/*
	// update the maximum shim region
	shim_buf = match_helper(pkt_ptr, payload_size, i-63, mptr, msize, mppos);
	if ( shim_buf.right-shim_buf.left > max_shim_region.right-max_shim_region.left ) {
		max_shim_region.m_fingerprint = shim_buf.m_fingerprint;
		max_shim_region.pid = shim_buf.pid;
		max_shim_region.left = shim_buf.left;
		max_shim_region.right = shim_buf.right;
	}
	*/
	if (org == target) {
		return false;
	}
	int left, right;
	left = 0;
	while (org_pos-left >= 0 && t_pos-left >= 0) {
		if (org[org_pos-left] == target[t_pos-left]){
			left += 1;
		}
		else {
			break;
		}
	}
	left -= 1;

	right = 0;
	while ( (org_pos+63+right < org_len) && (t_pos+63+right < t_len) ) {
		if (org[org_pos+63+right] == target[t_pos+63+right]) {
			right += 1;
		}
		else {
			break;
		}
	}
	right -= 1;

	// update result to max_shim_region
	if ( (right - left) > (max_shim_region.right - max_shim_region.left) ) {
		max_shim_region.org_left = org_pos - left;
		max_shim_region.org_right = org_pos + 63 + right;
		max_shim_region.left = t_pos - left;
		max_shim_region.right = t_pos + 63 + right;
		return true;
	}
	return false;
}

DEDUP::~DEDUP() {
	payload_t* pay_ptr = NULL;
	for (int i = 0; i < payloadT; i++) {
		pay_ptr = payload_store + i;
		if (pay_ptr->ptr != NULL) {
			free(pay_ptr->ptr);
			pay_ptr->ptr = NULL;
			pay_ptr->psize = 0;
		}
	}
	free(payload_store);
	payload_store = NULL;
}

ADD_MODULE(DEDUP, "dedup", "Redundency content elimination module for real-time packets!")
