// A BESS implementation of Packet-Dedup NF module

#ifndef BESS_MODULES_DEDUP_H_
#define BESS_MODULES_DEDUP_H_

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
const char* INIT_SHIM = "aaaaaaaa00000000";

using bess::utils::be16_t;
using bess::utils::be32_t;
using bess::utils::Ipv4Prefix;
typedef unsigned long long cycles_t;
inline cycles_t get_cycles() {
  cycles_t result;
  __asm__ __volatile__ ("rdtsc" : "=A" (result));
  return result;
}

class DEDUP final : public Module {
public:
  // the definition of the cell in payload store
  struct payload_t {
    char* ptr;
    int psize;
  };
  // the definition of the shim encode segment
  struct ShimRegion {
    u_int64_t m_fingerprint;
    long pid;
    int org_left;
    int org_right;
    int left;
    int right;
  };
  static const Commands cmds;
  DEDUP() : Module() { max_allowed_workers_ = Worker::kMaxWorkers; }
  CommandResponse CommandClear(const bess::pb::EmptyArg &arg);
  CommandResponse Init(const bess::pb::DEDUPArg &arg);

  void ProcessBatch(Context *ctx, bess::PacketBatch *batch) override;
  void encode_helper(char* spos, int target_num, int bit_len);
  int process_packet(char* pkt_ptr, int payload_size);
  long get_nextID();
  long get_time();
  cycles_t get_kcycles();
  bool valid_ID(long target_id);
  void insert_packet(char* pkt_ptr, int payload_size);
  char* get_payload(long payload_idx);
  void release_payload(long payload_idx);
  
  void insert_fingerprint(char* pkt_ptr, int payload_size);
  bool match_helper(char* org, int org_len, int org_pos, char* target, int t_len, int t_pos);
  ~DEDUP();

private:
  // time log
  long tmp_timer1, tmp_timer2;
  long long batch_cnt;
  long tt_timer1, tt_timer2;
  cycles_t timer1, timer2, timer3;
  cycles_t dt1, dt2;
  struct timeval tp;
  // trim packet
  bool trim_flag;
  ShimRegion max_shim_region;
  // the string buffer to hold the shim_region
  char shim_buf[17];
  // the next packet ID [0, maxID-1]
  long packet_id;
  // the payload store length
  long payloadT;
  // the max allowed packetID
  long maxID;
  // rolling hash tool
  window myRabin = window(FINGERPRINT_PT, WINDOW_SIZE);
  // unordered map to store fingerprint(pid, pos)
  std::unordered_map<u_int64_t, std::pair<int,int> > fingerprint_store;
  std::vector< std::tuple<u_int64_t, int> > fingerprint_list;
  // circular list to store payload
  payload_t* payload_store;
};

#endif  // BESS_MODULES_DEDUP_H_
