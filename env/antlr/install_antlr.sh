#!/bin/bash

THIS_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
echo "$THIS_DIR"

sudo cp ./antlr-4.7.1-complete.jar /usr/local/lib/

# edit ~./bash_profile
sudo echo >> $HOME/.bash_profile

sudo echo 'CLASSPATH="/usr/local/lib/antlr-4.7.1-complete.jar:$CLASSPATH"' >> ~/.bash_profile

sudo echo 'export CLASSPATH' >> ~/.bash_profile

# simplify the use of ANTLR to generate lexer and parser
sudo echo "alias antlr4='java -Dfile.encoding=UTF-8 -Xmx500M -cp \"/usr/local/lib/antlr-4.7.1-complete.jar:$CLASSPATH\" org.antlr.v4.Tool'" >> ~/.bash_profile

# simplify the use of ANTLR to test the generated code
sudo echo 'alias grun="java org.antlr.v4.gui.TestRig"' >> ~/.bash_profile
