pylabrecorder
=============

This module is a wrapper for pylab figures and other objects that records all actions sent to the figure and ax objects. 
When f.savefig() is called a modifiable script is saved in parallel which can recreate the figure.
It only works if the figures are created in the object oriented way. The documentation of the recorded_figure() function
shows how this is done.

you can run the unittests by calling 

prompt> python \_\_init\_\_.py

Tested for python 2.7. Dependencies matplotlib and numpy
