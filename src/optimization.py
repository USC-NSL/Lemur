import numpy as np
import gurobipy as gp


def maximizeMarginalRate(bounds, A, b, noLog=True):
    # A is a matrix and b is a column vector
    # bounds = ((min_f1, max_f1), ..., (min_fk, max_fk))
    # A f <= b
    # return (throughput_f1, ... throughput_fk) > (0, ..., 0) if feasible;
    # otherwise (0, ..., 0)
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
    """ Calculate marginal rate according to estimated
        throughput and SLO for each chain

    Parameter:
    bounds: the min/max SLOs
    throughputs: the computed throughput for all chains

    """
    assert len(bounds) == len(throughputs)
    return tuple(throughputs[i] - bounds[i][0] for i in range(len(bounds)))


def simpleTest():
    bounds = ((1, 4), (2, 3))
    A = np.array([[1, 0], [0, 1], [1, 1]])
    b = np.array([3, 10, 5])
    
    t = maximizeMarginalRate(bounds, A, b)
    print "bounds", bounds
    print "Throughput", t
    print "MarginalRate", marginalRate(bounds, t)

    
if __name__ == "__main__":
    simpleTest()
