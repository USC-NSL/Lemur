
import sys
import math
import paramiko
import atexit
import logging
import subprocess
import os
import pexpect

CONNECT_LOGGER = logging.getLogger("connect_logger")
CONNECT_LOGGER.setLevel(logging.DEBUG)

FH = logging.FileHandler('connect.log')
FH.setLevel(logging.DEBUG)
FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
FH.setFormatter(FORMATTER)

CONNECT_LOGGER.addHandler(FH)

HOST="68.181.218.3"
USER_NAME="root"

class myssh:
    def __init__(self, host, user, password):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=user, password=password)
        atexit.register(client.close)
        self.client = client
        self.chan = self.client.get_transport().open_session()

    def __call__(self, command):
        #stdin, stdout, stderr = self.client.exec_command(command)
        #sshdata = stdout.readlines()
        #for line in sshdata:
        #    print(line)
        self.chan.exec_command(command)
        #status = chan.recv_exit_status()
        key = True
        #print status
        
        while key:
            if self.chan.recv_ready():
                CONNECT_LOGGER.debug("%s", self.chan.recv(4096).decode('ascii'))
            if self.chan.exit_status_ready():
#                print("recv_exit_status: %s" % self.chan.recv_exit_status())
                key = False
#                self.client.close()
        
        return self.chan.recv_exit_status()

def check_empty_pattern():
    assert os.path.isfile('./pattern.txt')
    pattern_fp = open('./pattern.txt', 'r')
    choose = False
    past_pattern = -1
    chosen_pattern = 0
    change = False
    for line in pattern_fp:
        information = line.split("\t")
        assert len(information)>3
        if not choose:
            if int(information[1]) == 1:
                past_pattern = int(information[0])
                information[1] = 0
                change = True
            elif past_pattern == int(information[0]):
                information[2] = 1
            elif change and int(information[2])==0:
                chosen_pattern = int(information[0])
                information[1] = 1
                information[2] = 1
                choose = True
        else:
            if past_pattern == int(information[0]):
                information[2] = 1
    pattern_fp.close()
    if not change:
        chosen_pattern = -1
    return chosen_pattern

def stage_feasible(p4_filename):
    remote = myssh(HOST, USER_NAME, 'onl')
    CMD=""
    CMD+=("cd ~/bf-sde-8.2.0;")
    CMD+=(". ./set_sde.bash;")
    subprocess.call(['scp', p4_filename, '%s@%s:~/bf-sde-8.2.0/examples/%s.p4' % (USER_NAME, HOST, p4_filename.rsplit(".",1)[0])])
    CMD+=("./p4_build.sh examples/%s;" % p4_filename)
    status = remote(CMD)
    print(type(status))

    if status == 0:
        return True
    else:
        return False


def NFCP_memory_feasible():
    remote = myssh(HOST, USER_NAME, 'onl')
    CMD=""
    CMD+=("cd ~/bf-sde-8.2.0;")
    CMD+=(". ./set_sde.bash;")

    print("List all user-level configuration scripts:")
    subprocess.call(['ls', './user_level_examples'])

    user_filename = raw_input("Please input the NF chain configuration file: ")
    
    subprocess.call(['python', 'nfcp_compiler.py', '--file', user_filename])
    CMD+=("./p4_build.sh examples/%s.p4;" % user_filename.rsplit(".",1)[0] )
    status = remote(CMD)
    CONNECT_LOGGER.debug("final exit code: %d", status)
    subprocess.call(['scp', 'nf.p4', '%s@%s:~/bf-sde-8.2.0/examples/%s.p4' % (USER_NAME, HOST, user_filename.rsplit(".",1)[0])])
    CONNECT_LOGGER.debug("created filename = %s.p4 \n", user_filename.rsplit(".",1)[0])
    
    while (status != 0):
        pattern_bool = check_empty_pattern()
        if pattern_bool == -1:
            warnings.warn('no more pattern')
            break
        CONNECT_LOGGER.debug("re-entering configuration")
        subprocess.call(['python', 'nfcp_compiler.py', '--file', user_filename, '--iter'])
        remote2 = myssh(HOST, USER_NAME, 'onl')
        CMD=""
        CMD+=("cd ~/bf-sde-8.2.0;")
        CMD+=(". ./set_sde.bash;")
        CMD+=("./p4_build.sh examples/%s.p4;" % user_filename.rsplit(".",1)[0] )

        status = remote2(CMD)
        subprocess.call(['scp', 'nf.p4', '%s@%s:~/bf-sde-8.2.0/examples/%s.p4' % (USER_NAME, HOST, user_filename.rsplit(".",1)[0])])
    return


def lemur_check_logical_table(p4_file_name, log_file=None):
    """
    This function computes the minimal number of stages required by
    the P4 pipeline (p4_file_name) and checks whether it can be fit
    in a 12-stage switch hardware.
    Input: None
    Output: Bool
    """
    MAX_STAGE_NUM = 12
    # the default log file
    res_log_file = 'table_dependengency_group.log'
    if log_file!=None:
        res_log_file = log_file

    # modify file for testing
    tofino_old, tofino_new = 'tofino/', '/root/jianfeng/tofino/'
    edit_file_cmd = "sed -i'.bak' 's$%s$%s$g' %s" %(tofino_old, tofino_new, p4_file_name)
    edit_file = pexpect.spawn(edit_file_cmd)
    edit_file.read()

    target_file = 'nf.p4'
    target_dir = '/root/jianfeng/logical'
    send_file_cmd = 'scp %s %s@%s:%s/%s' %(p4_file_name, USER_NAME,HOST, target_dir, target_file)
    subprocess.call(['scp', p4_file_name, '%s@%s:%s/%s' %(USER_NAME,HOST, target_dir, target_file)])

    remote = myssh(HOST, USER_NAME, 'onl')
    CMD=""
    CMD+=("cd ~/bf-sde-8.2.0;")
    CMD+=(". ./set_sde.bash;")
    CMD+=("cd ~/jianfeng/logical;")
    CMD+=("p4-graphs %s --gen-dir ./gen > %s" %(target_file, res_log_file))
    status = remote(CMD)

    res_dir = './core/'
    res_log_cmd = 'scp %s@%s:%s/%s %s'%(USER_NAME,HOST,target_dir, res_log_file, res_dir)
    subprocess.call(['scp', '%s@%s:%s/%s' %(USER_NAME,HOST, target_dir, res_log_file), res_dir])

    # recover file
    recover_file_cmd = "sed -i'.bak' -e 's$%s$%s$' %s" %(tofino_new, tofino_old, p4_file_name)
    recover_file = pexpect.spawn(recover_file_cmd)
    recover_file.read()
    return

def NFCP_insert_table_entries(entry_filename):
    entry_dir = './test/entry/'
    target_file = entry_dir+entry_filename
    target_dir = '/root/jianfeng/en'
    send_file_cmd = 'scp %s %s@%s:%s/%s' %(target_file,USER_NAME,HOST, target_dir,entry_filename)
    send_file = pexpect.spawn(send_file_cmd)
    expect_result = send_file.expect([r'password:'],timeout=10)
    if expect_result==0:
        send_file.sendline('onl')
        send_file.read()
        #print(send_file)

    remote = myssh(HOST, USER_NAME, 'onl')
    CMD=""
    CMD+=("cd ~/bf-sde-8.2.0;")
    CMD+=(". ./set_sde.bash;")
    CMD+=("./run_bfshell.sh -f %s/%s;" %(target_dir, entry_filename))
    status = remote(CMD)
    return

if __name__ == "__main__":
    #NFCP_check_logical_table('nf.p4')
    NFCP_memory_feasible()
