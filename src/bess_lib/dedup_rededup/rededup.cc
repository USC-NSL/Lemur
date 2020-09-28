
#include "rededup.h"
#include "../utils/ether.h"
#include "../utils/ip.h"
#include "../utils/tcp.h"
#include "../utils/udp.h"

const Commands REDEDUP::cmds = {
	{"clear", "EmptyArg", MODULE_CMD_FUNC(&REDEDUP::CommandClear),
		Command::THREAD_UNSAFE}
};

CommandResponse REDEDUP::CommandClear(const bess::pb::EmptyArg &) {
	return CommandSuccess();
}

CommandResponse REDEDUP::Init(const bess::pb::REDEDUPArg &arg[[maybe_unused]]) {
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

void REDEDUP::ProcessBatch(Context *ctx, bess::PacketBatch *batch) {
	using bess::utils::Ethernet;
	using bess::utils::Ipv4;
	using bess::utils::Udp;
	using bess::utils::Tcp;
	// size_t = 64-bit unsigned data type, uint8_t = 1 byte data type
	int cnt = batch->cnt();
	char* payload = NULL;
	int payload_size = 0;

	for (int i = 0; i < cnt; i++) {
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
		payload = reinterpret_cast<char*>(udp + 1);
		payload_size = snbuf_ptr->data_len() - hdr_length;
		
		process_packet(payload, payload_size);
		
		// reset the packet length if the psize was changed
		if (t_shim_region.recover_flag) {
			snbuf_ptr->set_data_len(hdr_length + recover_psize);
			snbuf_ptr->set_total_len(hdr_length + recover_psize);
		}
	}
	//batch_cnt += 1;
	RunNextModule(ctx, batch);
}

int REDEDUP::process_packet(char* pkt_ptr, int payload_size) {
	/* This function processes the packet. First, scan the packet to find the shim encoder.
	If found, recover the packet payload. Then, for each packet, insert the payload to the payload store.
	:type pkt_ptr: char* 
	:type payload_size: int
	:type packet_id: int (next packet ID)
	*/
	// Initialization: set res_psize;
	recover_psize = payload_size;
	char* target = NULL;
	int target_len = 0;
	scan_shimregion(pkt_ptr, payload_size);
	if (t_shim_region.recover_flag) {
		target = (payload_store + t_shim_region.pid)->ptr;
		target_len = (payload_store + t_shim_region.pid)->psize;
		if (target != NULL && target_len > 0) {
			recover_psize = recover_packet(pkt_ptr, target);
		}
	}

	insert_packet(pkt_ptr, recover_psize);
	packet_id += 1;
	if (packet_id > maxID - 1) {
		packet_id = 0;
	}
	return packet_id;
}
void REDEDUP::scan_shimregion(char* pkt_ptr, int payload_size) {
	/* The function scans for the encoded shim region in a packet payload.
	:type pkt_ptr: char* (the pointer of the packet payload)
	:type payload_size: int (the length of the paylaod buffer)
	:rtype: void (do not return anything. The result is kept in t_shim_region)
	*/
	t_shim_region.recover_flag = false;
	if (pkt_ptr == NULL || payload_size <= 0)
		return;
	/* scan for the pos of 'aaaaaaaa' */
	int shim_cnt = 0;
	for (int i = 0; i < payload_size; i++) {
		if ( *(pkt_ptr+i) == 'a' ) {
			shim_cnt += 1;
			if (shim_cnt == 8){
				if ( valid_encoder(pkt_ptr, i+1, payload_size) ) {
					t_shim_region.recover_flag = true;
					t_shim_region.org_left = i-7;
					t_shim_region.org_right = i+8;
					t_shim_region.org_len = payload_size;
					t_shim_region.pid = decode_helper(pkt_ptr+i+1, 4);
					t_shim_region.left = decode_helper(pkt_ptr+i+5, 2);
					t_shim_region.right = decode_helper(pkt_ptr+i+7, 2);
					//LOG(INFO) << t_shim_region.pid << " " << t_shim_region.left << " " << t_shim_region.right << std::endl;
					break;
				}
			}
		}
		else {
			shim_cnt = 0;
		}
	}
}
bool REDEDUP::valid_encoder(char* pkt_ptr, int pos, int payload_size) {
	if (payload_size-pos < 8)
		return false;
	int cnt = 0;
	for (int i = pos; i < pos+8; i++){
		if (*(pkt_ptr+i)=='a')
			cnt += 1;
	}
	return (cnt < 8);
}
int REDEDUP::decode_helper(char* pkt_ptr, int bit_len) {
	/* The function returns the encoded number in the payload.
	:type pkt_ptr: char* (the payload pointer that points to the start byte)
	:type bit_len: int (the byte width)
	*/
	int res_num = 0;
	int curr;
	for(int i = 0; i < bit_len; i++) {
		curr = int(*(pkt_ptr+i));
		if (curr<0)
			curr += 256;
		res_num += base[i] * curr;
	}
	return res_num;
}
int REDEDUP::recover_packet(char* pkt_ptr, char* target) {
	/* This function recovers the packet payload from the payload store.
	:type pkt_ptr: char* (compressed packet payload)
	:type target: char** (payload in the store)
	*/
	int recover_psize = t_shim_region.right - t_shim_region.left + 1;
	char* recover_npos = pkt_ptr + t_shim_region.org_left;
	char* recover_ppos = target + t_shim_region.left;
	int rest_psize = t_shim_region.org_len - 1 - t_shim_region.org_right;
	char* rest_ppos = pkt_ptr + t_shim_region.org_right + 1;
	char* rest_npos = pkt_ptr + t_shim_region.org_left + t_shim_region.right - t_shim_region.left + 1;
	//bess::utils::Copy(rest_npos, rest_ppos, rest_psize, true);
	for(int i = rest_psize-1; i >= 0; i--) {
		*(rest_npos+i) = *(rest_ppos+i);
	}
	//bess::utils::Copy(recover_npos, recover_ppos, recover_psize, true);
	for(int i = recover_psize-1; i >= 0; i--) {
		*(recover_npos+i) = *(recover_ppos+i);
	}
	return (t_shim_region.org_len - 16 + recover_psize);
}
bool REDEDUP::valid_ID(long target_id) {
	/* The function tells whether the target_id is valid.
	:type target_id: long int (the target packet ID in the store)
	:rtype: bool (whether the payload is valid)
	*/
	if (target_id - packet_id > 0) {
		long convert_id = packet_id + maxID;
		if (convert_id - target_id >= 0) {
			return bool(packet_id - target_id <= payloadT);
		}
		else {
			return false;
		}
	}
	else {
		return bool(packet_id - target_id <= payloadT);
	}
}
void REDEDUP::insert_packet(char* pkt_ptr, int payload_size) {
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

REDEDUP::~REDEDUP() {
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

ADD_MODULE(REDEDUP, "rededup", "Recover packet content from the payload store!")
