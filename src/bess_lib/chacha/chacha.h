// A BESS implementation of CHACHA cipher module

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

using bess::utils::be32_t;
using bess::utils::be16_t;
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

  CommandResponse Init(const bess::pb::CHACHAArg &arg);
  void ProcessBatch(Context *ctx, bess::PacketBatch *batch) override;
  CommandResponse CommandClear(const bess::pb::EmptyArg &arg);

private:
  // This function runs the CHACHA cipher on the first 512-bit on the TCP
  // payload. If the packet does not have enough payload countent, the
  // function does the same processing until it reaches the payload's end.
  // |payload| is the pointer of the packet payload.
  // |payload_size| is the payload length.
  void process_packet(char* payload, int payload_size);

  // The chacha context for a packet.
  chacha_ctx chacha_ctx_;
  uint8_t tc_key_[32];
  uint8_t tc_iv_[8];
  //uint8_t tc_res[64];
  int chacha_rounds_; // 8, 20 (20 by default)
};

#endif  // BESS_MODULES_CHACHA_H_
