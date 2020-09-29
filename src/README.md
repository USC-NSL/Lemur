# Gurobi License Acquirement

(1) Install [Gurobi](https://www.gurobi.com/downloads/gurobi-optimizer-eula/) and configure environmental variables
```bash
export GUROBI_HOME="${PATH_TO_GUROBI}/gurobi${VERSION}/linux64"
export PATH="${PATH}:${GUROBI_HOME}/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${GUROBI_HOME}/lib"
```

(2) Install [Gurobi Python Interface](https://www.gurobi.com/documentation/8.0/quickstart_mac/the_gurobi_python_interfac.html)
```bash
python setup build
sudo python setup install
```

(3) Get [Gurobi license](https://www.gurobi.com/downloads/end-user-license-agreement-academic/) and install license



