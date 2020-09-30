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

HOST=""
USER_NAME= ""
PASSWORD = ""

class myssh:
    def __init__(self, host, user, password):
        """ Create SSH connection to PISA switch
        
        Parameter:
        host: host IP
        user: user account
        password: password to the switch

        """

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=user, password=password)
        atexit.register(client.close)
        self.client = client
        self.chan = self.client.get_transport().open_session()

    def __call__(self, command):
        """ Execute command on the switch
        
        Parameter:
        command: the execute command

        Returns:
        recv_exit_status: successfully execute command or not
        """
        self.chan.exec_command(command)
        key = True
        
        while key:
            if self.chan.recv_ready():
                CONNECT_LOGGER.debug("%s", self.chan.recv(4096).decode('ascii'))
            if self.chan.exit_status_ready():
                key = False
        
        return self.chan.recv_exit_status()

def stage_feasible(p4_filename):
    """ Compile p4 code at PISA switch

    Parameter:
    p4_filename: generated p4 file

    """
    remote = myssh(HOST, USER_NAME, PASSWORD)
    CMD=""
    CMD+=("cd ~/bf-sde-8.2.0;")
    CMD+=(". ./set_sde.bash;")
    subprocess.call(['scp', p4_filename, '%s@%s:~/bf-sde-8.2.0/examples/%s.p4' % (USER_NAME, HOST, p4_filename.rsplit(".",1)[0])])
    CMD+=("./p4_build.sh examples/%s;" % p4_filename)
    status = remote(CMD)

    if status == 0:
        return True
    else:
        return False



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
if __name__ == "__main__":
    lemur_check_logical_table('nf.p4')
