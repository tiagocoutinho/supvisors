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

from supervisor.loggers import getLogger
from supervisor.xmlrpc import Faults, RPCError

from supvisors.addressmapper import AddressMapper
from supvisors.commander import Starter, Stopper
from supvisors.context import Context
from supvisors.infosource import SupervisordSource
from supvisors.listener import SupervisorListener
from supvisors.options import SupvisorsServerOptions
from supvisors.sparser import Parser
from supvisors.statemachine import FiniteStateMachine
from supvisors.statscompiler import StatisticsCompiler
from supvisors.strategy import RunningFailureHandler


class Supvisors(object):
    """ The Supvisors class. """

    # logger output
    LOGGER_FORMAT = '%(asctime)s %(levelname)s %(message)s\n'

    def __init__(self, supervisord):
        """ Initialization of the attributes. """
        # store this instance in supervisord to ensure persistence
        supervisord.supvisors = self
        # get options from config file
        server_options = SupvisorsServerOptions()
        server_options.realize()
        self.options = server_options.supvisors_options
        # create logger
        stdout = supervisord.options.nodaemon
        self.logger = getLogger(self.options.logfile, self.options.loglevel,
            Supvisors.LOGGER_FORMAT, True, self.options.logfile_maxbytes,
            self.options.logfile_backups, stdout)
        # configure supervisor info source
        self.info_source = SupervisordSource(supervisord)
        # set addresses and check local address
        self.address_mapper = AddressMapper(self.logger)
        self.address_mapper.addresses = self.options.address_list
        if not self.address_mapper.local_address:
            raise RPCError(Faults.SUPVISORS_CONF_ERROR,
                'local host unexpected in address list: {}'.format(self.options.address_list))
        # create context data
        self.context = Context(self)
        # create application starter and stopper
        self.starter = Starter(self)
        self.stopper = Stopper(self)
        # create statistics handler
        self.statistician = StatisticsCompiler(self)
        # create the failure handler of crashing processes
        self.failure_handler = RunningFailureHandler(self)
        # create state machine
        self.fsm = FiniteStateMachine(self)
        # check parsing
        try:
            self.parser = Parser(self)
        except:
            self.logger.warn('cannot parse deployment file: {}'.format(self.options.deployment_file))
            self.parser = None
        # create event subscriber
        self.listener = SupervisorListener(self)
