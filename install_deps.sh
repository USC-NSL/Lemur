#!/bin/bash

THIS_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
echo "$THIS_DIR"

# Install JRE/JDK (Java)
sudo apt-get update
sudo apt-get install default-jdk

# Install pip
sudo apt-get install python-pip
#sudo pip install --upgrade pip

# Install ANTLR
cd ./env/antlr
sudo bash ./install_antlr.sh
pwd
cd ../..

# Install Graph-Easy
sudo apt-get install graphviz
sudo cpan Graph:Easy

# Install python lib
# paramiko
pip install paramiko --user
pip isntall Pexpect --user
pip install numpy --user


