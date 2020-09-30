"""
* This file provides a graph struct to be used by Lemur compiler.
"""

from collections import defaultdict 
import copy

class Graph:
    def __init__(self,vertices):
        self.V= vertices
        self.graph = defaultdict(list)
        self.route = []

    def addEdge(self,u,v):
        self.graph[u].append(v)

    def printAllPathsUtil(self, u, d, visited, path):
        visited[u]= True
        path.append(u)

        if u ==d:
            # print path
            self.route.append(list(path))
        else:
            for i in self.graph[u]:
                if visited[i]==False: 
                    self.printAllPathsUtil(i, d, visited, path)
        path.pop()
        visited[u]= False

    def printAllPaths(self,s, d):
        visited =[False]*(self.V) 
        path = []
        self.printAllPathsUtil(s, d,visited, path)       
        # print self.route
        route = list(self.route)
        self.route = []
        return route
