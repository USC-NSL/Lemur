#!/bin/bash

THIS_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
echo "$THIS_DIR"

# Install JRE/JDK (Java)
sudo apt-get update
sudo apt-get install default-jdk

#
# Install pip
# Note: if you do not have Python + pip installed, first install
# them with pyenv. See https://github.com/pyenv/pyenv for more
# details.
# 
# git clone https://github.com/pyenv/pyenv.git ~/.pyenv
# echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bash_profile
# echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bash_profile
# echo -e 'if command -v pyenv 1>/dev/null 2>&1; then\n  eval "$(pyenv init -)"\nfi' >> ~/.bash_profile
#

sudo python -m easy_install --upgrade pyOpenSSL

# Install ANTLR
cd ./env/antlr
sudo bash ./install_antlr.sh
pwd
cd ../..

# Install Graph-Easy
sudo apt-get install graphviz
sudo cpan Graph:Easy

# Install python lib
pip install paramiko --user
pip install Pexpect --user
pip install numpy --user
pip install termcolor --user
