#!/usr/bin/python
#-*- coding: utf-8 -*-

# ======================================================================
# Copyright 2016 Julien LE CLEACH
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ======================================================================

import os
import random

from mock import patch, Mock

from supervisor.loggers import Logger
from supervisor.rpcinterface import SupervisorNamespaceRPCInterface
from supervisor.states import RUNNING_STATES, STOPPED_STATES


class DummyAddressMapper:
    """ Simple address mapper with an empty addresses list. """
    def __init__(self):
        self.addresses = ['127.0.0.1', '10.0.0.1', '10.0.0.2', '10.0.0.3', '10.0.0.4', '10.0.0.5']
        self.local_address = '127.0.0.1'
    def filter(self, address_list):
        return address_list
    def valid(self, address):
        return address in self.addresses


class DummyOptions:
    """ Simple options with dummy attributes. """
    def __init__(self):
        # configuration options
        self.internal_port = 65100
        self.event_port = 65200
        self.synchro_timeout = 10
        self.auto_fence = True
        self.deployment_file = ''
        self.deployment_strategy = 0
        self.conciliation_strategy = 0
        self.stats_periods = 5, 15, 60
        self.stats_histo = 10
        # additional process configuration
        self.procnumbers = {'xclock': 2}


class MockedSupvisors:
    """ Simple supvisors with all dummies. """
    def __init__(self):
        # use a dummy address mapper and options
        self.address_mapper = DummyAddressMapper()
        self.options = DummyOptions()
        # mock the context
        from supvisors.context import Context
        self.context = Mock(spec=Context)
        self.context.__init__()
        self.context.addresses = {}
        self.context.applications = {}
        # simple mocks
        self.deployer = Mock()
        self.fsm = Mock()
        self.pool = Mock()
        self.requester = Mock()
        self.statistician = Mock()
        self.failure_handler = Mock()
        # mock the supervisord source
        from supvisors.infosource import SupervisordSource
        self.info_source = Mock(spec=SupervisordSource)
        self.info_source.get_env.return_value = {'SUPERVISOR_SERVER_URL': 'http://127.0.0.1:65000', 
            'SUPERVISOR_USERNAME': '', 'SUPERVISOR_PASSWORD': ''}
        # mock by spec
        from supvisors.listener import SupervisorListener
        self.listener = Mock(spec=SupervisorListener)
        self.logger = Mock(spec=Logger)
        from supvisors.sparser import Parser
        self.parser = Mock(spec=Parser)
        from supvisors.commander import Starter, Stopper
        self.starter = Mock(spec=Starter)
        self.stopper = Mock(spec=Stopper)
        from supvisors.supvisorszmq import SupvisorsZmq
        self.zmq = Mock(spec=SupvisorsZmq)
        self.zmq.__init__()


class DummyRpcHandler:
    """ Simple supervisord RPC handler with dummy attributes. """
    def __init__(self):
        self.rpcinterface = Mock(supervisor='supervisor_RPC', supvisors='supvisors_RPC')


class DummyRpcInterface:
    """ Simple RPC proxy. """
    def __init__(self):
        from supvisors.rpcinterface import RPCInterface
        supervisord = DummySupervisor()
        # cretae rpc interfaces to have a skeleton
        # create a Supervisor RPC interface
        self.supervisor = SupervisorNamespaceRPCInterface(supervisord)
        # create a mocked Supvisors RPC interface 
        def create_supvisors(*args, **kwargs):
            return MockedSupvisors()
        with patch('supvisors.rpcinterface.Supvisors', side_effect=create_supvisors):
            self.supvisors = RPCInterface(supervisord)


class DummyHttpServer:
    """ Simple supervisord RPC handler with dummy attributes. """
    def __init__(self):
        self.handlers = [DummyRpcHandler(), Mock()]
    def install_handler(self, handler, condition):
        self.handlers.append(handler)


class DummyServerOptions:
    """ Simple supervisord server options with dummy attributes. """
    def __init__(self):
        # build a fake server config
        self.server_configs = [{'section': 'inet_http_server', 'port': 1234,
            'username': 'user', 'password': 'p@$$w0rd'}]
        self.serverurl = 'url'
        self.mood = 'mood'
        self.nodaemon = True
        # build a fake http config
        self.httpservers = [[None, DummyHttpServer()]]
        self.httpserver = self.httpservers[0][1]
        # prepare storage for close_httpservers test
        self.storage = None
    def close_httpservers(self):
        self.storage = self.httpservers


class DummyProcess:
    """ Simple supervisor process with simple attributes. """
    def __init__(self, command, autorestart):
        self.state = 'STOPPED'
        self.spawnerr = ''
        # create dummy config
        class DummyObject: pass
        self.config = DummyObject()
        self.config.command = command
        self.config.autorestart = autorestart
    def give_up(self):
       self.state = 'FATAL'
    def change_state(self, state):
       self.state = state

class DummySupervisor:
    """ Simple supervisor with simple attributes. """
    def __init__(self):
        self.supvisors = MockedSupvisors()
        self.configfile = 'supervisord.conf'
        self.options = DummyServerOptions()
        self.process_groups = {'dummy_application':
            Mock(config='dummy_application_config', 
                processes={'dummy_process_1': DummyProcess('ls', True),
                    'dummy_process_2': DummyProcess('cat', False)})}


class DummyHttpContext:
    """ Simple HTTP context for web ui views. """
    def __init__(self, template):
        import supvisors
        module_path = os.path.dirname(supvisors.__file__)
        self.template = os.path.join(module_path, template)
    
    
# note that all dates ('now') are different
ProcessInfoDatabase = [
    {'description': '', 'pid': 80886, 'stderr_logfile': '', 'stop': 1473888084,
        'logfile': './log/late_segv_cliche01.log', 'exitstatus': 0, 'spawnerr': '', 'now': 1473888091,
        'group': 'crash', 'name': 'late_segv', 'statename': 'STARTING', 'start': 1473888089, 'state': 10,
        'stdout_logfile': './log/late_segv_cliche01.log'},
    {'description': 'Exited too quickly (process log may have details)', 'pid': 0, 'stderr_logfile': '',
        'stop': 1473888156, 'logfile': './log/segv_cliche01.log', 'exitstatus': 0,
        'spawnerr': 'Exited too quickly (process log may have details)', 'now': 1473888156,
        'group': 'crash', 'name': 'segv', 'statename': 'BACKOFF', 'start': 1473888155, 'state': 30,
        'stdout_logfile': './log/segv_cliche01.log'}, 
    {'description': 'Sep 14 05:18 PM', 'pid': 0, 'stderr_logfile': '', 'stop': 1473887937,
        'logfile': './log/firefox_cliche01.log', 'exitstatus': 0, 'spawnerr': '', 'now': 1473888161,
        'group': 'firefox', 'name': 'firefox', 'statename': 'EXITED', 'start': 1473887932, 'state': 100,
        'stdout_logfile': './log/firefox_cliche01.log'},
    {'description': 'pid 80877, uptime 0:01:20', 'pid': 80877, 'stderr_logfile': '', 'stop': 0,
        'logfile': './log/xclock_cliche01.log', 'exitstatus': 0, 'spawnerr': '', 'now': 1473888166,
        'group': 'sample_test_1', 'name': 'xclock', 'statename': 'STOPPING', 'start': 1473888078, 'state': 40,
        'stdout_logfile': './log/xclock_cliche01.log'},
    {'description': 'pid 80879, uptime 0:01:19', 'pid': 80879, 'stderr_logfile': '', 'stop': 0,
        'logfile': './log/xfontsel_cliche01.log', 'exitstatus': 0, 'spawnerr': '', 'now': 1473888171,
        'group': 'sample_test_1', 'name': 'xfontsel', 'statename': 'RUNNING', 'start': 1473888079, 'state': 20,
        'stdout_logfile': './log/xfontsel_cliche01.log'},
    {'description': 'Sep 14 05:21 PM', 'pid': 0, 'stderr_logfile': '', 'stop': 1473888104,
        'logfile': './log/xlogo_cliche01.log', 'exitstatus': -1, 'spawnerr': '', 'now': 1473888176,
        'group': 'sample_test_1', 'name': 'xlogo', 'statename': 'STOPPED', 'start': 1473888085, 'state': 0,
        'stdout_logfile': './log/xlogo_cliche01.log'},
    {'description': 'No resource available', 'pid': 0, 'stderr_logfile': '', 'stop': 0,
        'logfile': './log/sleep_cliche01.log', 'exitstatus': 0, 'spawnerr': 'No resource available',
        'now': 1473888181, 'group': 'sample_test_2', 'name': 'sleep', 'statename': 'FATAL', 'start': 0, 'state': 200,
        'stdout_logfile': './log/sleep_cliche01.log'},
    {'description': 'Sep 14 05:22 PM', 'pid': 0, 'stderr_logfile': '', 'stop': 1473888130,
        'logfile': './log/xeyes_cliche01.log', 'exitstatus': 0, 'spawnerr': '', 'now': 1473888186,
        'group': 'sample_test_2', 'name': 'yeux_00', 'statename': 'EXITED', 'start': 1473888086, 'state': 100,
        'stdout_logfile': './log/xeyes_cliche01.log'},
    {'description': 'pid 80882, uptime 0:01:12', 'pid': 80882, 'stderr_logfile': '', 'stop': 0,
        'logfile': './log/xeyes_cliche01.log', 'exitstatus': 0, 'spawnerr': '', 'now': 1473888196,
        'group': 'sample_test_2', 'name': 'yeux_01', 'statename': 'RUNNING', 'start': 1473888086, 'state': 20,
        'stdout_logfile': './log/xeyes_cliche01.log'}]


def database_copy():
    """ Return a copy of the whole database. """
    return [info.copy() for info in ProcessInfoDatabase]

def any_process_info():
    """ Return a copy of any process in database. """
    return random.choice(ProcessInfoDatabase).copy()

def any_stopped_process_info():
    """ Return a copy of any stopped process in database. """
    return random.choice([info for info in ProcessInfoDatabase if info['state'] in STOPPED_STATES]).copy()

def any_running_process_info():
    """ Return a copy of any running process in database. """
    return random.choice([info for info in ProcessInfoDatabase if info['state'] in RUNNING_STATES]).copy()

def any_process_info_by_state(state):
    """ Return a copy of any process in state 'state' in database. """
    return random.choice([info for info in ProcessInfoDatabase if info['state'] == state]).copy()

def process_info_by_name(name):
    """ Return a copy of a process named 'name' in database. """
    return next((info.copy() for info in ProcessInfoDatabase if info['name'] == name), None)
