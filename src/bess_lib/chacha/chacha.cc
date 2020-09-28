
#include "chacha.h"
#include "../utils/ether.h"
#include "../utils/ip.h"
#include "../utils/tcp.h"
#include "../utils/udp.h"



//------------------------------------------------------------------
// init_ctx()
//
// Init a given ChaCha context by setting state to zero and
// setting the given number of rounds.
//------------------------------------------------------------------
void chacha_init_ctx(chacha_ctx *ctx, uint8_t rounds) {
	uint8_t i;
	for (i = 0 ; i < 16 ; i++) {
		ctx->state[i] = 0;
	}
	ctx->rounds = rounds;
}
//------------------------------------------------------------------
// chacha_doublerounds()
//
// Perform rounds/2 number of chacha_doublerounds.
// TODO: Change output format to 16 words.
//------------------------------------------------------------------
void chacha_doublerounds(uint8_t output[64], const uint32_t input[16], uint8_t rounds) {
	uint32_t x[16];
	int32_t i;
	for (i = 0;i < 16;++i) {
		x[i] = input[i];
	}
	for (i = rounds ; i > 0 ; i -= 2) {
		QUARTERROUND( 0, 4, 8,12)
		QUARTERROUND( 1, 5, 9,13)
		QUARTERROUND( 2, 6,10,14)
		QUARTERROUND( 3, 7,11,15)

		QUARTERROUND( 0, 5,10,15)
		QUARTERROUND( 1, 6,11,12)
		QUARTERROUND( 2, 7, 8,13)
		QUARTERROUND( 3, 4, 9,14)
	}

	for (i = 0;i < 16;++i) {
		x[i] = PLUS(x[i], input[i]);
	}
	for (i = 0;i < 16;++i) {
		U32TO8_LITTLE(output + 4 * i, x[i]);
	}
}
//------------------------------------------------------------------
// init()
//
// Initializes the given cipher context with key, iv and constants.
// This also resets the block counter.
//------------------------------------------------------------------
void chacha_init(chacha_ctx *x, uint8_t *key, uint32_t keylen, uint8_t *iv)
{
  if (keylen == 256) {
    // 256 bit key.
    x->state[0]  = U8TO32_LITTLE(SIGMA + 0);
    x->state[1]  = U8TO32_LITTLE(SIGMA + 4);
    x->state[2]  = U8TO32_LITTLE(SIGMA + 8);
    x->state[3]  = U8TO32_LITTLE(SIGMA + 12);
    x->state[4]  = U8TO32_LITTLE(key + 0);
    x->state[5]  = U8TO32_LITTLE(key + 4);
    x->state[6]  = U8TO32_LITTLE(key + 8);
    x->state[7]  = U8TO32_LITTLE(key + 12);
    x->state[8]  = U8TO32_LITTLE(key + 16);
    x->state[9]  = U8TO32_LITTLE(key + 20);
    x->state[10] = U8TO32_LITTLE(key + 24);
    x->state[11] = U8TO32_LITTLE(key + 28);
  }

  else {
    // 128 bit key.
    x->state[0]  = U8TO32_LITTLE(TAU + 0);
    x->state[1]  = U8TO32_LITTLE(TAU + 4);
    x->state[2]  = U8TO32_LITTLE(TAU + 8);
    x->state[3]  = U8TO32_LITTLE(TAU + 12);
    x->state[4]  = U8TO32_LITTLE(key + 0);
    x->state[5]  = U8TO32_LITTLE(key + 4);
    x->state[6]  = U8TO32_LITTLE(key + 8);
    x->state[7]  = U8TO32_LITTLE(key + 12);
    x->state[8]  = U8TO32_LITTLE(key + 0);
    x->state[9]  = U8TO32_LITTLE(key + 4);
    x->state[10] = U8TO32_LITTLE(key + 8);
    x->state[11] = U8TO32_LITTLE(key + 12);
  }

  // Reset block counter and add IV to state.
  x->state[12] = 0;
  x->state[13] = 0;
  x->state[14] = U8TO32_LITTLE(iv + 0);
  x->state[15] = U8TO32_LITTLE(iv + 4);
}
//------------------------------------------------------------------
// next()
//
// Given a pointer to the next block m of 64 cleartext bytes will
// use the given context to transform (encrypt/decrypt) the
// block. The result will be stored in c.
//------------------------------------------------------------------
void chacha_next(chacha_ctx *ctx, uint8_t *m, uint8_t *m_end) {
  // Temporary internal state x.
  uint8_t x[64];
  uint8_t i;
  // Update the internal state and increase the block counter.
  chacha_doublerounds(x, ctx->state, ctx->rounds);
  ctx->state[12] = PLUSONE(ctx->state[12]);
  if (!ctx->state[12]) {
    ctx->state[13] = PLUSONE(ctx->state[13]);
  }

  // XOR the input block with the new temporal state to
  // create the transformed block.
  if (m+64 > m_end) {
    return;
  }
  /*
  for (i = 0 ; i < 64 ; ++i) {
    c[i] = m[i] ^ x[i];
  }
  */
  uint64_t *m_pos;
  uint64_t *x_pos;
  for (i = 0; i < 8; i++) {
  	m_pos = (uint64_t*)(m) + i;
  	x_pos = (uint64_t*)(x) + i;
  	*m_pos ^= *x_pos;
  }
}


const Commands CHACHA::cmds = {
	{"clear", "EmptyArg", MODULE_CMD_FUNC(&CHACHA::CommandClear),
		Command::THREAD_UNSAFE}
};

CommandResponse CHACHA::CommandClear(const bess::pb::EmptyArg &) {
	return CommandSuccess();
}

CommandResponse CHACHA::Init(const bess::pb::CHACHAArg &arg[[maybe_unused]]) {
	chacha_rounds = CHACHA_ROUNDS;
	memcpy(tc_key, default_key, sizeof(default_key));
	memcpy(tc_iv, default_iv, sizeof(default_iv));
	return CommandSuccess();
}

void CHACHA::ProcessBatch(Context *ctx, bess::PacketBatch *batch) {
	using bess::utils::Ethernet;
	using bess::utils::Ipv4;
	using bess::utils::Udp;
	using bess::utils::Tcp;
	int cnt = batch->cnt();
	int i;
	char* payload = NULL;
	int payload_size = 0;
	size_t hdr_length;
	for (i=0; i < cnt; i++) {
		bess::Packet *snbuf_ptr = batch->pkts()[i];
		Ethernet *eth = snbuf_ptr->head_data<Ethernet *>();
		Ipv4 *ip = reinterpret_cast<Ipv4 *>(eth + 1);
		// ip->header_length (1 word = 4 bytes)
		size_t ip_bytes = ip->header_length << 2;
		if (ip->protocol == Ipv4::Proto::kUdp) {
			Udp *udp = reinterpret_cast<Udp *>(reinterpret_cast<uint8_t *>(ip) + ip_bytes);
			hdr_length = sizeof(*eth) + sizeof(*ip) + sizeof(*udp);
			payload = reinterpret_cast<char*>(udp + 1);
			payload_size = snbuf_ptr->data_len() - hdr_length;
		}
		else if (ip->protocol == Ipv4::Proto::kTcp) {
			Tcp *tcp = reinterpret_cast<Tcp *>(reinterpret_cast<uint8_t *>(ip) + ip_bytes);
			hdr_length = sizeof(*eth) + sizeof(*ip) + sizeof(*tcp);
			payload = reinterpret_cast<char*>(tcp + 1);
			payload_size = snbuf_ptr->data_len() - hdr_length;
		}
		else {
			continue;
		}

		process_packet(payload, payload_size);

	}
	RunNextModule(ctx, batch);
}
void CHACHA::process_packet(char* payload, int payload_size) {
	/* This function runs the chacha cipher program on the first 512-bit on the TCP/UDP packet
	payload. If the packet does not have enough number of bits, the function simply returns
	without any processing.
	:type payload: char* (the pointer of the packet payload)
	:type payload_size: int (the length of the payload buffer)
	:rtype: void (do not return anything. Modify the packet in place.)
	*/
	chacha_init_ctx(&cha_ctx, chacha_rounds);
	chacha_init(&cha_ctx, tc_key, 128, tc_iv);

	// loop here
	char* payload_pos = NULL;
	int byte_cnt = 0;
	for(byte_cnt=0; byte_cnt + 512/8 <= payload_size; byte_cnt += 512/8) {
		payload_pos = (char *)(payload+byte_cnt);
		chacha_next(&cha_ctx, (uint8_t *)payload_pos, (uint8_t *)(payload_pos+512/8) );
		//memcpy(payload_pos, tc_res, sizeof(tc_res));
	}
	return;
}

CHACHA::~CHACHA() {
	return;
}


ADD_MODULE(CHACHA, "chacha", "CHACHA-20 stream cipher program!")

