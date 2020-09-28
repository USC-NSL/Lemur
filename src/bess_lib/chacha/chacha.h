
#ifndef BESS_MODULES_CHACHA_H_
#define BESS_MODULES_CHACHA_H_

#include <sys/types.h>
#include <unistd.h>
#include <vector>
#include <tuple>
#include <unordered_map>
#include <time.h>

#include "../module.h"
#include "../pb/module_msg.pb.h"
#include "../utils/ip.h"
#include "../utils/tcp.h"
#include "../utils/udp.h"

//------------------------------------------------------------------
// Macros.
//------------------------------------------------------------------
#define CHACHA_ROUNDS 8
// 1500/(512/8)
#define CHACHA_DATA_LOOPS 23

// Basic 32-bit operators.
#define ROTATE(v,c) ((uint32_t)((v) << (c)) | ((v) >> (32 - (c))))
#define XOR(v,w) ((v) ^ (w))
#define PLUS(v,w) ((uint32_t)((v) + (w)))
#define PLUSONE(v) (PLUS((v), 1))

// Little endian machine assumed (x86-64).
#define U32TO8_LITTLE(p, v) (((uint32_t*)(p))[0] = v)
#define U8TO32_LITTLE(p) (((uint32_t*)(p))[0])
#define QUARTERROUND(a, b, c, d) \
  x[a] = PLUS(x[a],x[b]); x[d] = ROTATE(XOR(x[d],x[a]),16); \
  x[c] = PLUS(x[c],x[d]); x[b] = ROTATE(XOR(x[b],x[c]),12); \
  x[a] = PLUS(x[a],x[b]); x[d] = ROTATE(XOR(x[d],x[a]), 8); \
  x[c] = PLUS(x[c],x[d]); x[b] = ROTATE(XOR(x[b],x[c]), 7);

//------------------------------------------------------------------
// Constants.
//------------------------------------------------------------------
static const uint8_t SIGMA[17] = "expand 32-byte k";
static const uint8_t TAU[17]   = "expand 16-byte k";
static const uint8_t default_key[32] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                         			0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                         			0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                         			0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
static const uint8_t default_iv[8]   = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

using bess::utils::be16_t;
using bess::utils::be32_t;
using bess::utils::Ipv4Prefix;

// the chacha cipher context struct
typedef struct {
	uint32_t state[16];
	uint8_t rounds;
} chacha_ctx;
void chacha_init_ctx(chacha_ctx *cctx, uint8_t rounds);
void chacha_doublerounds(uint8_t output[64], const uint32_t input[16], uint8_t rounds);
void chacha_init(chacha_ctx *cctx, uint8_t *key, uint32_t keylen, uint8_t *iv);
void chacha_next(chacha_ctx *cctx, const uint8_t *m, const uint8_t *m_end, uint8_t *c);


class CHACHA final : public Module {
public:
	static const Commands cmds;
	CHACHA() : Module() { max_allowed_workers_ = Worker::kMaxWorkers; }
	CommandResponse CommandClear(const bess::pb::EmptyArg &arg);
	CommandResponse Init(const bess::pb::CHACHAArg &arg);
	// the chacha context for each packet
	chacha_ctx cha_ctx;
	uint8_t tc_key[32];
	uint8_t tc_iv[8];
	//uint8_t tc_res[64];
	void ProcessBatch(Context *ctx, bess::PacketBatch *batch) override;
	void process_packet(char* payload, int payload_size);
	~CHACHA();
private:
	int chacha_rounds; // 8, 20 (20 by default)
};

#endif  // BESS_MODULES_CHACHA_H_
