"""
@author: Nick Rhinehart
nrhineha@cs.cmu.edu
nrhine1@gmail.com
Carnegie Mellon University 

Simple pythonic socket interface for

Visual Structure From Motion by
Changchang Wu
ccwu@cs.washington.edu
"""

from multiprocessing import Process
from collections import OrderedDict
import os, pdb
import time
import socket
import sys
import thread
import subprocess, signal

import type_util as typeu
import data.vsfm_ui as vsfm_ui

cur_dir = os.path.dirname(os.path.realpath(__file__))

# programmatically make functions based on py dictionary of commands
class VSFMCommander(object):
    def __init__(self, socket):
        self.functions = OrderedDict()
        self.socket = socket
        self.create_functions_from_dictionary(vsfm_ui.menu)

    def __repr__(self):
        s = 'VSFM Commander on socket {}. Function List:\n--\n'.format(self.socket.getsockname()[1])
        for fn, (fid, _) in self.functions.items():
            s += '{}(*args, **kwargs) ({})\n'.format(fn, fid)

        return s

    # create functions with prefixes depending on menu / dictionary hierarchy
    def create_functions_from_dictionary(self, d, prefix = ''):
        for k,v in d.items():
            if isinstance(k, str) and k.find('menu') == 0:
                self.create_functions_from_dictionary(v, prefix = '_'.join(k.split('_')[1:]) + '_')
            else:
                fid, func_name = k, prefix + v

                assert(not hasattr(self, func_name))

                func = self.create_single_function(fid, func_name)
                setattr(self, func_name, func)
                self.functions[func_name] = fid, func

    # create functions that send commands over socket... these functions will return after
    # sending the command
    def create_single_function(self, fid, func_name):
        def _(*args, **kwargs):
            cmd = '{}{}{} {}\n'.format(fid, 
                                       'c' if 'control' in kwargs else '',
                                       's' if 'shift' in kwargs else '',
                                       args[0] if len(args) > 0 else '')

            print "sending command over port {}: ({},{}".format(self.socket.getsockname()[1], func_name, cmd.strip())
            self.socket.sendall(cmd)
        return _                        

# main interface class
class VSFMInterface(object):
    
    @typeu.member_initializer
    def __init__(self, 
                 vsfm_binary_fn = '/home/nrhineha/dev/vsfm/bin/VisualSFM', 
                 port = None,
                 host = 'localhost'):
        self.init()

    def init(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.port is None:
            tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tmp_sock.bind(('', 0))
            self.port = tmp_sock.getsockname()[1]
            tmp_sock.close()
            del tmp_sock
            print "will bind to port: {}".format(self.port)

        self.vsfm_process = Process(target = self.start_program)
        self.vsfm_process.start()
        
        def handle_sigint(sig, frame):
            self.close()
            raise KeyboardInterrupt()

        def handle_sigquit(sig, frame):
            self.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_sigint)
        signal.signal(signal.SIGQUIT, handle_sigquit)

        for _ in range(10):
            try:
                self.sock.connect((self.host, self.port))
                break
            except:
                time.sleep(0.1)
        time.sleep(0.05)

        self.commander = VSFMCommander(self.sock)
        self.add_functions_from_commander()
        self.create_overrides()

    def restart(self):
        try:
            self.commander.file_exit_program()
        except:
            pass
        try:
            self.vsfm_process.join()
        except:
            pass

        self.port = None
        self.init()
        
    def add_functions_from_commander(self):
        for func_name, (fid, func) in self.commander.functions.items():
            setattr(self, func_name, func)

    # create overriding functions... e.g. dense_reconstruction requires a 
    # path but will fail silently if you don't pass one
    def create_overrides(self):
        def reconstruct_dense(path = 'dense_recon'):
            path = os.path.abspath(path)
            if not os.path.isdir(path):
                os.mkdir(path)
            
            fid, rd_func = self.commander.functions['sfm_reconstruct_dense']
            rd_func(path)
        setattr(self, 'sfm_reconstruct_dense', reconstruct_dense)

    def start_program(self):
        self.cmd = '{} listen+log {}'.format(self.vsfm_binary_fn, self.port)
        self.args = self.cmd.split(' ')
        self.vsfm_subprocess = subprocess.Popen(self.args)
    
    def close(self):
        self.commander.file_exit_program()
        self.sock.close()

        
