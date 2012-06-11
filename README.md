pylabrecorder
=============

Wrapper for pylab figures and other objects that records all actions sent to the figure and ax objects. When f.savefig() is called a modifiable script is saved in parallel that can recreate the figure.