# Network Function Control Plane Compiler
The repo contains the `Network Function Control Plane Compiler`, or `nfcp_compiler` for short.<br>

As for most of network function (NF) programming systems, they mainly try to provide three different components. They are:<br>
(1) Programming NFs (e.g. NetBricks, BESS)<br>
(2) Chaining and Executing NFs (e.g. NetBricks, BESS)<br>
(3) Scaling and Orchestrating the Execution of NFs (e.g. E2, Metron) <br>

In this work, we provide a NF service chain framework which mainly focuses on the (2), i.e. chaining NFs and executing NFs. Our motivation comes from the emerging high-performance programmable switching chips. We want to embrace both the benefits from high-throughput and fast hardware switches and the programmability and flexibility from the tranditional software network functions. One way to understand this project is to think about offloading part of NFs from the software side to the programmable switches<br>

Given that the programmable switches read P4 packet processing language, it is obvious that we should provide a efficient programming architecture that enables the following goals:<br>
(1) fast development of new NFs (in P4 packet processing language)<br>
(2) fast and easy deployment, i.e. getting correct P4 code and BESS code for both sides<br>
(3) efficient NF chaining<br>

Our work nfcp_compiler is aimed to solve the above three problems.<br>

# How to Use nfcp_compiler
(1) Clone this repo<br>
```bash
$ git clone https://github.com/USC-NSL/P4-BESS.git
```

(2) Visit the `parser-sd` directory and place your configuration file in this directory<br>
Here is an example of NFCP user-level configuration script.<br>
(Please check `example_lb.conf`)<br>
```raw
SilkRoad -> IPv4Forward
```

(3) Run nfcp_compiler<br>
Let's assume that you are trying to compile `example_lb.conf`.<br>
You run the nfcp_compiler by typing the following.<br>
```bash
$ python nfcp_compiler.py
```

Then, the compiler asks you for the input file name. You should type the targeted configuration file here.<br>
```bash
example_lb.conf
```
The nfcp_compiler will output two files. `nf.p4` is the final P4 code that incorporates all P4 NF nodes, while `nf.bess` is the final BESS configuration script that includes all BESS modules.<br>

(4) Set up the NF-chain conditions<br>
For 'nf.p4', you have to set up the corresponding conditions for each service paths.<br>
```raw
action network_service_path_selector_table_1_hit() {
	meta.service_path_id = 1;
}

action network_service_path_selector_table_1_miss() {
}

table network_service_path_selector_table_1 {
	key = {
	// Input your matching fields here
	// e.g. hdr.ipv4.dstAddr
	}
	actions = {
		network_service_path_selector_table_1_hit;
		network_service_path_selector_table_1_miss;
	}
	default_action = network_service_path_selector_table_1_miss;
	size = 10;
}
```

For example, if you want to match destination IP address for service path 1, you should add `hdr.ipv4.dstAddr` into the key in the `network_service_path_selector_table_1`.<br>

(5) Finish<br>
After this, run `nf.p4` on the P4 switch and run `nf.bess` on BESS servers.<br>

You should get what you want.<br>

# The List of Programming Tasks
* Task - programming script design
* 1. Design the header definition part (DONE)
* 2. Design the parser specification part (DONE)
* 3. Include the external P4 network function libraries (e.g. SilkRoad.lib) (DONE)
* 4. Design the deparser specification part (DONE)
* 5. Test the code generator with the simplest library (basic forwarding / dumb switch) (DONE)
* 6. Test the code generator with a more complex library (silkroad.lib) (DONE)
* 7. Test the system with multiple service paths and many NF nodes (complex NF chain example) (ON GOING)
* 8. Test the system together with BESS system (NOT FINISHED YET)
* 9. TBD

'Parallel' branch differ from 'script design' branch in the following files:
1.  example_l2.conf <br />
    |--- Add extra test cases including multiple service paths, multiple BESS nodes, multiple bounces chain, and nickname argument passing  

2.  nf.bess <br />
    |--- This is the automatically generated BESS script according to user input configuration file.

3.  nf_chain_parser.py <br />
    |--- 'trim-nickname_arg': This function is used to parse module nickname and return the real module definition string <br />
    |--- 'trim_name_arg': This function is used to separate an input string with parenthesis, and return module name & module arguments <br />
    |--- 'nf_chain_parse_line': Add extra input argument to the function so that module nickname cases are checked (line #88 to #106) <br />
    |--- 'nf_fn_parse_line': Cut nickname from '::' expression in input string and return the key name to store in dictionary <br />
    |--- 'nf_arg_parse_line': Cut nickname from '=' expression in input string and return the key name to store in dictionary <br />
    |--- 'nf_chain_parser_main': Add nickname parsing (line #168 to #177) and extra input argument (line #181) 

4.  nfcp_bess_generation.py <br />
    |--- This script is used to generate final runnable BESS script with BESS node list as input

5.  nfcp_compiler.py <br />
    |--- Add 'writing to BESS script file' (line #57 to #67)

6.  nfcp_nf_node_wBess.py <br />
    |--- Add more artificial BESS nodes and add node variables/members to record argument & nickname. Two functions are added to store nickname & arg
    
Note that in order to link some files to correct the dependencies (i.e. the library import) should be checked while merging files
