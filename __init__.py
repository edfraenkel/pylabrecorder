from os import listdir, popen
from pickle import dumps, loads
from pylab import *
from numpy import *
import pylab
from matplotlib.axes import Subplot

class NotRecordable(Exception):
  pass

class ObjectRecorder(object):
  """
  Records all function calls and attribute access to the object and allows 
  to save them as a program. Parent class of FigureRecorder.
  This class doesn't need to be instantiated by the user.
  """
  def __init__(self, obj, opcodes=None, names=None, argument_data=None, known_objects=None):
    if opcodes == None:
      opcodes = list()
    if names == None:
      names = dict()
    if argument_data == None:
      argument_data = list()
    if known_objects == None:
      known_objects = list()
    super(ObjectRecorder, self).__init__()
    self._recorder_object = obj
    self._opcodes = opcodes
    self._names = names
    self._argument_data = argument_data
    if hasattr(obj, '__name__') and obj.__name__ in known_objects and \
       obj == known_objects[obj.__name__]:
      self._recorder_name = obj.__name__
    else:
      basename = self.__simplify_name(type(obj).__name__)
      num = names.get(basename, 0) + 1
      self._names[basename] = num
      self._recorder_name = '%s%s' % (basename, num)
    self._known_objects = known_objects
    self._initialized = True

  def __getattr__(self, attrname):
    retval = getattr(self._recorder_object, attrname)
    if retval is not None:
      retval = type(self)(retval, self._opcodes, self._names, self._argument_data, self._known_objects)
    self._opcodes.append(('__getattr__', self, attrname, retval))
    return retval
    
  def __getitem__(self, index):
    retval = self._recorder_object.__getitem__(index)
    if retval is not None:
      retval = type(self)(retval, self._opcodes, self._names, self._argument_data, self._known_objects)
    self._opcodes.append(('__getitem__', self, index, retval))
    return retval
  
    
  def __clean(self, obj, obj_list=None):
    # to prevent infinite recursion for recursive datatypes
    if not obj_list:
      obj_list = list()
    for other_obj in obj_list:
      if other_obj is obj:
        return obj
    obj_list.append(obj)
    # recursively clean dictionary objects
    if isinstance(obj, dict):
      return dict([(self.__clean(key, obj_list), self.__clean(value, obj_list)) for (key, value) in obj.items()])
    # recursively clean lists
    if isinstance(obj, list):
      return [self.__clean(x, obj_list) for x in obj]
    # recursively clean tuples
    if isinstance(obj, tuple):
      return tuple([self.__clean(x, obj_list) for x in obj])
    # recursively clean sets
    if isinstance(obj, set):
      return set([self.__clean(x, obj_list) for x in obj])
    # unwrap the object if it is wrapped by an ObjectRecorder object
    if isinstance(obj, ObjectRecorder):
      return obj._recorder_object
    # return the the 'cleaned' object
    return obj
  
  def __call__(self, *args, **kwargs):
    retval = self._recorder_object(*self.__clean(args), **self.__clean(kwargs))
    if retval is not None:
      retval = type(self)(retval, self._opcodes, self._names, self._argument_data, self._known_objects)
    self._opcodes.append(('__call__', self, (args, kwargs), retval))
    return retval
    
  def __setattr__(self, attrname, attrvalue):
    if '_initialized' in self.__dict__:
      self._opcodes.append(('__setattr__', self, (attrname, attrvalue), None))
      setattr(self._recorder_object, attrname, self.__clean(attrvalue))
    else:
      super(ObjectRecorder, self).__setattr__(attrname, attrvalue)
    
  def __repr__(self):
    self._known_objects[self._recorder_name] = self._recorder_object
    return self._recorder_name
  
  def __stringify_argument(self, arg, raise_error=True):
    strarg = repr(arg)
    try:
      eval(strarg, dict(), self._known_objects)
    except Exception, e:
      can_be_evaluated = False
    else:
      can_be_evaluated = True
    if len(strarg) < 100:
      is_large = False
    else:
      is_large = True
    try:
      data = dumps(arg)
      loads(data) # extra precaution to see wether it can also be unpickled
    except Exception, e:
      can_be_pickled = False
    else:
      can_be_pickled = True
    if not can_be_pickled and not can_be_evaluated:
      if raise_error:
        raise NotRecordable(arg)
      else:
        return repr(arg)
    if (can_be_pickled and is_large) or (not can_be_evaluated):
      if data not in self._argument_data:
        self._argument_data.append(data)
      strarg = '__data%s' % self._argument_data.index(data)
    return strarg
    
  def __string_arguments(self, args, kwargs):
    try:
      return (True, (
        [self.__stringify_argument(arg) for arg in args], 
        ["%s=%s" % (name, self.__stringify_argument(arg)) for name, arg in kwargs.items()]
      ))
    except NotRecordable, e:
      sys.stderr.write("WARNING: One of the arguments can't be recorded: %s\n" % e)
      return (False, (
        [self.__stringify_argument(arg, raise_error=False) for arg in args], 
        ["%s=%s" % (name, self.__stringify_argument(arg, raise_error=False)) for name, arg in kwargs.items()]
      ))
      
    
  _class_member_replacement_strings = dict()
  def __simplify_name(self, name):
    return self._class_member_replacement_strings.get(name, name)
  
  def __compress_statements(self, statements):
    lvalues, rvalues, argument_strs, recordable = [list(l) for l in zip(*statements)]
    i = 0
    while True:
      if not i < len(rvalues) - 1:
        break
      if lvalues[i] == rvalues[i+1] and rvalues[i+1] not in rvalues[i+2:] and \
         rvalues[i+1] not in self._known_objects and recordable[i+1]:
        lvalues.pop(i)
        rvalues.pop(i+1)
        recordable.pop(i+1)
        argument_strs[i] = argument_strs[i] + argument_strs.pop(i+1)
      i += 1
    for i in xrange(len(lvalues)):
      if lvalues[i] not in rvalues[i+1:] and \
         lvalues[i] not in self._known_objects:
        lvalues[i] = None
    statements = zip(lvalues, rvalues, argument_strs, recordable)
    return statements
  
  def __get_statements(self):
    statements = list()
    for op_type, op_obj, op_args, retval in self._opcodes:
      recordable = True
      if op_type == '__call__':
        recordable, (strargs, strkwargs) = self.__string_arguments(*op_args)
        argument_str = '(%s)' % ", ".join(strargs + strkwargs)
      elif op_type == '__getitem__':
        argument_str = '[%s]' % op_args
      elif op_type == '__getattr__':
        argument_str = '.%s' % op_args
      elif op_type == '__setattr__':
        try:
          value = self.__stringify_argument(op_args[1])
        except NotRecordable:
          value = self.__stringify_argument(op_args[1], raise_error=False)
          recordable = False
        argument_str = '.%s = %s' % (op_args[0], value)
      lvalue = retval._recorder_name if retval is not None else None
      rvalue = op_obj._recorder_name
      statements.append((lvalue, rvalue, argument_str, recordable))
    return self.__compress_statements(statements)
    
  def _get_recorder_header_code(self):
    lines = [
      "#!/usr/bin/env python", 
      "from pickle import dumps, loads"
    ]  
    return lines
  
  def _get_recorder_central_code(self):
    lines = list()
    lines.append('# this method will be called at the end of the script')
    lines.append('def recorded_code():')
    for lvalue, rvalue, argument_str, recordable in self.__get_statements():
      if lvalue:
        lines.append('  %s = %s%s' % (lvalue, rvalue, argument_str))
      else:
        lines.append('  %s%s' % (rvalue, argument_str))
      if not recordable:
        lines[-1] = '#' + lines[-1]
    return lines
    
  def _get_recorder_data_storage_code(self):
    if not self._argument_data:
      return list()
    lines = list()
    lines.append("# The next line%s contain%s too large and non human readable data" % 
      (('', 's') if len(self._argument_data) == 1 else ('s', '')))
    for i, data in enumerate(self._argument_data):
      lines.append("__data%s = loads(%s)" % (i, repr(data)))
    return lines
    
  def _get_recorder_footer_code(self):
    lines = [
      "recorded_code()"
    ]
    return lines
  
  def get_recorder_code(self):
    lines = (self._get_recorder_header_code() + [""]
           + self._get_recorder_central_code() + [""]
           + self._get_recorder_data_storage_code() + [""]
           + self._get_recorder_footer_code())
    return lines

def unwrap_recorder(x):
  if hasattr(x, '_recorder_object'):
    return x._recorder_object
  else:
    return x

class FigureRecorder(ObjectRecorder):
  """
  An instance of this class is returned by the recorded_figure() method. 
  This class doesn't need to be instantiated by the user.
  """
  _class_member_replacement_strings = {
    'Figure':      'f', 
    'AxesSubplot': 'ax', 
    'list':        'l'
  }
  
  def _get_recorder_header_code(self):
    lines = super(FigureRecorder, self)._get_recorder_header_code()
    lines.append('from pylab import *')
    lines.append('try:')
    lines.append('  from myplotlib import my_setup')
    lines.append('except ImportError, e:')
    lines.append('  print "No my_setup available"') 
    lines.append('from optparse import OptionParser')
    lines.append('import matplotlib.pyplot')
    lines.append('matplotlib.pyplot.rcParams[\'legend.numpoints\'] = 1')
    return lines
    
  def _get_recorder_footer_code(self):
    lines = list()
    lines.append('import __main__                                              '.rstrip(' '))
    lines.append('recorded_code()                                              '.rstrip(' ')) 
    lines.append('filename = __main__.__file__.replace(\'.pdf.py\', \'.pdf\')  '.rstrip(' '))
    lines.append('assert __main__ != filename                                  '.rstrip(' ')) 
    lines.append('assert filename.endswith(\'.pdf\')                           '.rstrip(' '))
    lines.append('savefig(filename)                                            '.rstrip(' ')) 
    # lines.append('show()                                                       '.rstrip(' ')) 
    return lines
    
  def savefig(self, *args, **kwargs):
    fname = args[0] if args else kwargs['fname']
    scriptfile = open('%s.py' % fname, 'w')
    popen('chmod +x \'%s.py\'' % fname)
    for line in self.get_recorder_code():
      scriptfile.write('%s\n' % line)
    self._recorder_object.savefig(*args, **kwargs)

  def __call__(self, *args, **kwargs):
    # unwrap stuff if it doesn't appear to be a matplotlib or pylab object
    retval = super(FigureRecorder, self).__call__(*args, **kwargs)
    if hasattr(retval, '_recorder_object'):
      sname = repr(retval._recorder_object)
      if 'matplotlib' not in sname and 'pylab' not in sname:
        return retval._recorder_object  
    return retval
  
__doc__ = """
Wrapper for pylab figures that that allows them to be saved as scripts.
"""

def recorded_figure(*args, **kwargs):
  """
  Records everything that is done to the wrapped pylab figure and it's 
  resulting classes.
  When f.savefig(<fname>) is called a python script with the name <fname>.py
  is saved. This script can later be changed to reproduce the plot in a
  modified version.
  
  >>> from util import *
  >>> from pylab import *

  >>> f = recorded_figure(figsize=(8, 8))
  >>> ax1 = f.add_subplot(121)
  >>> ax1
  ax1
  >>> ax2 = f.add_subplot(122)
  >>> ax1.plot([1, 2, 5, 7], color='red');
  l1
  >>> ax2.plot(array([sin(0.1*n) for n in xrange(10)]), color='red')
  l2
  >>> ax2.get_xlim()
  (0.0, 9.0)

  >>> f.savefig('test_recorded_figure.pdf')
  """
  return FigureRecorder(figure, known_objects={'figure': figure})(*args, **kwargs)
  
if __name__ == "__main__":
    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS)
    
      