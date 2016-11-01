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

from time import time

from supervisors.strategy import conciliate
from supervisors.ttypes import AddressStates, SupervisorsStates
from supervisors.utils import supervisors_short_cuts


class AbstractState(object):
    """ Base class for a state with simple entry / next / exit actions """

    def __init__(self, supervisors):
        self.supervisors = supervisors
        supervisors_short_cuts(self, ['context', 'logger'])
        self.address = supervisors.address_mapper.local_address

    def enter(self):
        pass

    def next(self):
        pass

    def exit(self):
        pass


class InitializationState(AbstractState):

    def enter(self):
        self.context.master_address = ''
        self.start_date = int(time())
        # re-init remotes that are not isolated
        for status in self.context.addresses.values():
            if not status.in_isolation():
                # do NOT use state setter as transition may be rejected
                status._state = AddressStates.UNKNOWN
                status.checked = False

    def next(self):
        # cannot get out of this state without local supervisor RUNNING
        addresses = self.context.running_addresses()
        if self.address in addresses:
            if len(self.context.unknown_addresses()) == 0:
                # synchro done if the state of all remotes is known
                return SupervisorsStates.DEPLOYMENT
            # if synchro timeout reached, stop synchro and work with known remotes
            if (time() - self.start_date) > self.supervisors.options.synchro_timeout:
                self.logger.warn('synchro timed out')
                return SupervisorsStates.DEPLOYMENT
            self.logger.debug('still waiting for remote supervisors to synchronize')
        else:
            self.logger.debug('local address {} still not RUNNING'.format(self.address))
        return SupervisorsStates.INITIALIZATION

    def exit(self):
        # force state of missing Supervisors instances
        self.supervisors.context.end_synchro()
        # arbitrarily choice : master address is the 'lowest' address among running remotes
        addresses = self.supervisors.context.running_addresses()
        self.logger.info('working with boards {}'.format(addresses))
        self.context.master_address = min(addresses)


class DeploymentState(AbstractState):

    def enter(self):
        # define ordering iaw Remotes
        for application in self.context.applications.values():
            application.update_start_sequence()
            application.update_status()
        # only Supervisors master deploys applications
        if self.context.master:
            self.supervisors.deployer.deploy_applications(self.context.applications.values())

    def next(self):
        if self.supervisors.deployer.check_deployment():
                return SupervisorsStates.CONCILIATION if self.context.conflicting() else SupervisorsStates.OPERATION
        return SupervisorsStates.DEPLOYMENT


class OperationState(AbstractState):

    def next(self):
        # check if master and local are still RUNNING
        if self.context.addresses[self.address].state != AddressStates.RUNNING:
            return SupervisorsStates.INITIALIZATION
        if self.context.addresses[self.context.master_address].state != AddressStates.RUNNING:
            return SupervisorsStates.INITIALIZATION
        # check duplicated processes
        if self.context.conflicting():
            return SupervisorsStates.CONCILIATION
        return SupervisorsStates.OPERATION


class ConciliationState(AbstractState):

    def enter(self):
        # the Supervisors Master auto-conciliate conflicts
        if self.context.master:
            conciliate(self.supervisors, self.supervisors.options.conciliation_strategy, self.context.conflicts())

    def next(self):
        # check if master and local are still RUNNING
        if self.context.addresses[self.address].state != AddressStates.RUNNING:
            return SupervisorsStates.INITIALIZATION
        if self.context.addresses[self.context.master_address].state != AddressStates.RUNNING:
            return SupervisorsStates.INITIALIZATION
        # check conciliation
        if not self.context.conflicting():
            return SupervisorsStates.OPERATION
        return SupervisorsStates.CONCILIATION


class FiniteStateMachine:
    """ This class implements a very simple behaviour of FiniteStateMachine based on a single event.
    A state is able to evaluate itself for transitions. """

    def __init__(self, supervisors):
        """ Reset the state machine and the associated context """
        self.supervisors = supervisors
        supervisors_short_cuts(self, ['context', 'deployer', 'logger'])
        self.update_instance(SupervisorsStates.INITIALIZATION)
        self.instance.enter()

    def state_string(self):
        """ Return the application state as a string. """
        return SupervisorsStates._to_string(self.state)

    def next(self):
        """ Send the event to the state and transitions if possible.
        The state machine re-sends the event as long as it transitions. """
        next_state = self.instance.next()
        while next_state != self.state and next_state in self.__Transitions[self.state]:
            self.instance.exit()
            self.update_instance(next_state)
            self.logger.info('Supervisors in {}'.format(self.state_string()))
            self.instance.enter()
            next_state = self.instance.next()

    def update_instance(self, state):
        """ Change the current state.
        The method also triggers the publication of the change. """
        self.state = state
        self.instance = self.__StateInstances[state](self.supervisors)
        # publish RemoteStatus event
        self.supervisors.publisher.send_supervisors_status(self)

    def on_timer_event(self):
        """ Periodic task used to check if remote Supervisors instance are still active.
        This is also the main event on this state machine. """
        self.context.on_timer_event()
        self.next()
        # master can fix inconsistencies if any
        if self.context.master:
            self.deployer.deploy_marked_processes(self.context.marked_processes())
        # check if new isolating remotes and return the list of newly isolated addresses
        return self.context.handle_isolation()

    def on_tick_event(self, address, when):
        """ This event is used to refresh the data related to the address. """
        self.context.on_tick_event(address, when)
        # could call the same behaviour as onTimerEvent if necessary

    def on_process_event(self, address, event):
        """ This event is used to refresh the process data related to the event and address.
        This event also triggers the deployer. """
        process = self.context.on_process_event(address, event)
        # trigger deployment work if needed
        if process and self.deployer.in_progress():
            self.deployer.deploy_on_event(process)

    # serialization
    def to_json(self):
        """ Return a JSON-serializable form of the SupervisorState """
        return {'state': self.state_string()}

    # Map between state enumeration and class
    __StateInstances = {
        SupervisorsStates.INITIALIZATION: InitializationState,
        SupervisorsStates.DEPLOYMENT: DeploymentState,
        SupervisorsStates.OPERATION: OperationState,
        SupervisorsStates.CONCILIATION: ConciliationState
    }

    # Transitions allowed between states
    __Transitions = {
        SupervisorsStates.INITIALIZATION: [ SupervisorsStates.DEPLOYMENT ],
        SupervisorsStates.DEPLOYMENT: [ SupervisorsStates.OPERATION, SupervisorsStates.CONCILIATION ],
        SupervisorsStates.OPERATION: [ SupervisorsStates.CONCILIATION, SupervisorsStates.INITIALIZATION ],
        SupervisorsStates.CONCILIATION: [ SupervisorsStates.OPERATION, SupervisorsStates.INITIALIZATION ]
   }
