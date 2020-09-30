// A BESS implementation of Packet-Recovery-Dedup NF module

#ifndef BESS_MODULES_REDEDUP_H_
#define BESS_MODULES_REDEDUP_H_

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

#include "rabinpoly.h"
#define Payload_STORE_SIZE 1000000
#define MAX_PKT_ID 10000000000
#define MAX_PKT_SIZE 1500
const u_int64_t FINGERPRINT_PT = 0xbfe6b8a5bf378d83LL;
const unsigned int WINDOW_SIZE = 64;

using bess::utils::be16_t;
using bess::utils::be32_t;
using bess::utils::Ipv4Prefix;
typedef unsigned long long cycles_t;
inline cycles_t get_cycles() {
  cycles_t result;
  __asm__ __volatile__ ("rdtsc" : "=A" (result));
  return result;
}

// the dedup recover module
class REDEDUP final : public Module {
public:
  int base[4] = {1, 256, 65536, 16777216};
  //int base[5] = {1, 255, 65025, 16581375, 4228250625};
  // the definition of the cell in payload store
  struct payload_t {
    char* ptr;
    int psize;
  };
  // the definition of the shim encode segment
  struct ShimRegion {
    long pid;
    int org_left;
    int org_right;
    int org_len;
    int left;
    int right;
    bool recover_flag;
  };
  static const Commands cmds;
  REDEDUP() : Module() { max_allowed_workers_ = Worker::kMaxWorkers; }
  CommandResponse CommandClear(const bess::pb::EmptyArg &arg);
  CommandResponse Init(const bess::pb::REDEDUPArg &arg);
  
  void ProcessBatch(Context *ctx, bess::PacketBatch *batch) override;

  int process_packet(char* pkt_ptr, int payload_size);
  int decode_helper(char* pkt_ptr, int bit_len);
  void scan_shimregion(char* pkt_ptr, int payload_size);
  bool valid_encoder(char* pkt_ptr, int pos, int payload_size);
  bool valid_ID(long target_id);
  int recover_packet(char* pkt_ptr, char* target);
  void insert_packet(char* pkt_ptr, int payload_size);
  ~REDEDUP();

private:
  // time log
  long tmp_timer1, tmp_timer2;
  long long batch_cnt;
  long tt_timer1, tt_timer2;
  cycles_t timer1, timer2, timer3;
  cycles_t dt1, dt2;
  struct timeval tp;

  int recover_psize;
  ShimRegion t_shim_region;
  // the next packet ID [0, maxID-1]
  long packet_id;
  // the payload store length
  long payloadT;
  // the max allowed packetID
  long maxID;
  // rolling hash tool
  window myRabin = window(FINGERPRINT_PT, WINDOW_SIZE);
  // circular list to store payload
  payload_t* payload_store;
};

#endif  // BESS_MODULES_REDEDUP_H_
