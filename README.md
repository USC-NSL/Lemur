# Lemur Compiler
Lemur is a flexible and high-performance packet processing framework that meets SLOs in cross-platform NFV.

Lemur works as a cross-platform compiler. It parses NF chains from a user-level specification, and considers all available hardware resources to generate an placement scheme for NFs. In Lemur, NFs from the same NF chain may be placed at different platforms. Lemur considers the fundemental tradeoff between performance and programmability to achieve a higher throughput.

## Features
(1) Flexible configuration of multiple network service chains <br>
(2) Efficient heuristic algorithm for hardware deployment decision <br>
(3) Involve 'minimum bounce', 'HW preferred', 'SW preferred', 'Greedy' algorithms as comparison altermatives <br>
(4) Fast deployment on heterogeneous hardware (automatic code generation for P4 and BESS code)<br>

# Build Instructions

## Dependencies
(1) Clone this repo<br>
```bash
$ git clone https://github.com/USC-NSL/Lemur.git
```

(2) Install dependencies<br>
``` bash
$ ./install_deps.sh
```

(3) Get Gurobi License<br>
Please follow the instructions in /src folder to get your Gurobi license

## Configuring Lemur
(1) Visit the `src` directory and define your service chain configuration file in the `user_level_example` directory<br>
Here is an example of Lemur user-level configuration script.<br>
(Please check `chain_1.conf`)<br>
```raw
AESCBC()-> VLANPush()->IPv4Forward()
```

(2) Configure your SLOs, hardware setting and profiled number<br>
`device.txt`: NIC information for your BESS server <br>
`module_data.txt`: Profiled CPU cycles for each BESS modules on your BESS server <br>
`max_delay.txt`: Your max delay setting for your service chains. One row contains only one delay number for a service chain. The row order matches with the service chain order. <br>
`chain_rate.txt`: Your [min, max] throughput settings for your service chains. One row contains one [min, max] throughput requirement for a service chain. The row order macthes with the service chain order. <br>

## Running Lemur
(1) Run Lemur compiler with heuristic algorithm in `src` directory<br>
Let's assume that you are trying to compile `chain_0_1_2_3.conf`. You will run the Lemur compiler by typing the following.<br>
```bash
$ python lemur_heuristic_compiler.py -f chain_0_1_2_3
```

The Lemur compiler will output two files. `nf.p4` is the final P4 code that incorporates all P4 NF nodes, while `intel_nic1.bess` is the final BESS configuration script that includes all BESS modules. The naming of BESS script is based on the nic information provided in `device.txt`. <br>

(optional) If you would like to compare with the brutal force algorithm and other alternatives, type the following in `src` directory.
```bash
$ python lemur_compiler.py -f chain_0_1_2_3
```
The default algorithm is the brutal force algorithm. To change to other alternatives, you can set `-m {$MODE_NUMBER}` to switch. For more detail, please use `-h` to view options. 

(2) Download P4 code and BESS script to your hardware and compile. Due to NDA regulations, please directly contact your PISA switch vendor for compilation problem. Note that you will still need to register table entries for your traffic to guarantee service chains are operated to your traffic.<br>


## Additional Instructions
For Lemur to properly check stage constraints, you can leverage /src/connect.py file to set up your ssh connection to your PISA switch. We have removed our testbed's information in the script, so please change the setting for your experiment setup.

# MILP Problem Formulation
We include our MILP problem formulation in `MILP_formulation.pdf`.
