import numpy as np
import gurobipy as gp


# bounds = ((min_f1, max_f1), ..., (min_fk, max_fk))
# A f <= b
# A is a matrix and b is a column vector
# return (throughput_f1, ... throughput_fk) > (0, ..., 0) if feasible;
# otherwise (0, ..., 0)
def maximizeMarginalRate(bounds, A, b, noLog=True):
    numFlow = len(bounds)
    (numRow, numCol) = A.shape
    assert numRow == len(b) and numCol == numFlow

    model = gp.Model()
    # define variables
    flows = gp.tuplelist(t for t in range(numFlow))
    t = model.addVars(flows, vtype=gp.GRB.CONTINUOUS, name="t_")
    for f in flows:
        (minRate, maxRate) = bounds[f]
        t[f].setAttr(gp.GRB.Attr.LB, minRate)
        t[f].setAttr(gp.GRB.Attr.UB, maxRate)
    model.update()

    # define the objective function
    model.setObjective(t.sum(), gp.GRB.MAXIMIZE)

    # define constraints
    for row in range(numRow):
        expr = 0
        for f in flows:
            expr += A[row, f] * t[f]
        model.addConstr(expr <= b[row], name="c_{0}".format(row))

    # solve optimization problem (LP)
    if noLog:
        model.setParam("LogToConsole", 0)
    model.optimize()
    status = model.status
    throughputs = [0] * numFlow
    if status == gp.GRB.Status.OPTIMAL:
        for f in flows:
            throughputs[f] = t[f].X
    elif status == gp.GRB.Status.INFEASIBLE:
        pass
    else:
        assert False, "Solver returns neither OPTIMAL nor INFEASIBLE."
    return tuple(throughputs)


def marginalRate(bounds, throughputs):
    assert len(bounds) == len(throughputs)
    return tuple(throughputs[i] - bounds[i][0] for i in range(len(bounds)))


def simpleTest():
#    bounds = ((1, 4), (2, 3))
    bounds= ((0000000.0, 40000000000.0), (000000000.0, 40000000000.0), (0000000.0, 40000000000.0), (0000000.0, 40000000000.0))
#    A = np.array([[1, 0], [0, 1], [1, 1]])
    A = np.array([[0, 1.0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0], [0, 0, 0, 1.0], [0.0, 1.0, 1.0, 2.0]])
#    b = np.array([3, 10, 5])
    b = np.array([12240000000000.0, 1020000000000.0, 1020000000000.0, 1020000000000.0, 40000000000])
    
    t = maximizeMarginalRate(bounds, A, b)
#    assert t[0] >= 1 and t[1] >= 2 and sum(t) == 5
    print "bounds", bounds
    print "Throughput", t
    print "MarginalRate", marginalRate(bounds, t)

    
if __name__ == "__main__":
    simpleTest()
