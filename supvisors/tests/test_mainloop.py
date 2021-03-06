#!/usr/bin/python
#-*- coding: utf-8 -*-

# ======================================================================
# Copyright 2017 Julien LE CLEACH
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

import sys
import unittest

from mock import call, patch, DEFAULT
from threading import Thread

from supvisors.tests.base import MockedSupvisors, DummyRpcInterface


class MainLoopTest(unittest.TestCase):
    """ Test case for the mainloop module. """

    def setUp(self):
        """ Create a Supvisors-like structure and patch getRPCInterface. """
        self.supvisors = MockedSupvisors()
        self.rpc_patch = patch('supvisors.mainloop.getRPCInterface')
        self.mocked_rpc = self.rpc_patch.start()

    def tearDown(self):
        """ Remove patch of getRPCInterface. """
        self.rpc_patch.stop()

    def test_creation(self):
        """ Test the values set at construction. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        self.assertIsInstance(main_loop, Thread)
        self.assertIs(self.supvisors, main_loop.supvisors)
        self.assertFalse(main_loop.loop)
        self.assertIs(self.supvisors.zmq.internal_subscriber, main_loop.subscriber)
        self.assertIs(self.supvisors.zmq.puller, main_loop.puller)
        self.assertDictEqual({'SUPERVISOR_SERVER_URL': 'http://127.0.0.1:65000', 
            'SUPERVISOR_USERNAME': '', 'SUPERVISOR_PASSWORD': ''}, main_loop.env)
        self.assertEqual(1, self.mocked_rpc.call_count)
        self.assertEqual(call('localhost', main_loop.env), self.mocked_rpc.call_args)

    def test_get_loop(self):
        """ Test the get_loop method. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        self.assertFalse(main_loop.get_loop())
        main_loop.loop = True
        self.assertTrue(main_loop.get_loop())

    def test_stop(self):
        """ Test the stopping of the main loop thread. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # try to stop main loop before it is started
        with self.assertRaises(RuntimeError):
            main_loop.stop()
        # stop main loop after it is started
        main_loop.loop = True
        with patch.object(main_loop, 'join') as mocked_join:
            main_loop.stop()
            self.assertFalse(main_loop.loop)
            self.assertEqual(1, mocked_join.call_count)

    @patch.multiple('supvisors.mainloop.zmq.Poller', register=DEFAULT, unregister=DEFAULT, poll=DEFAULT)
    def test_run(self, register, unregister, poll):
        """ Test the running of the main loop thread. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # configure patches
        main_loop.subscriber.receive.side_effect = [Exception, 'subscription']
        main_loop.puller.receive.side_effect = [Exception, ('pull', 'data')]
        # patch 4 loops
        with patch.object(main_loop, 'get_loop', side_effect=[True]*4+[False]):
            # patch zmq calls: 2 loops for subscriber, 2 loops for puller
            effects = [{main_loop.subscriber.socket: 1}]*2+[{main_loop.puller.socket: 1}]*2
            poll.side_effect = effects
            with patch.multiple(main_loop, send_remote_comm_event=DEFAULT, send_request=DEFAULT) as mocked_loop:
                main_loop.run()
                # test that poll was called 4 times
                self.assertEqual([call(500)]*4, poll.call_args_list)
                # test that register was called twice
                self.assertEqual([call(main_loop.subscriber.socket, 1), call(main_loop.puller.socket, 1)], register.call_args_list)
                # test that unregister was called twice
                self.assertEqual([call(main_loop.puller.socket), call(main_loop.subscriber.socket)], unregister.call_args_list)
                # test that send_remote_comm_event was called once
                self.assertEqual([call(u'event', '"subscription"')], mocked_loop['send_remote_comm_event'].call_args_list)
                # test that send_request was called once
                self.assertEqual([call('pull', 'data')], mocked_loop['send_request'].call_args_list)

    def test_check_address(self):
        """ Test the protocol to get the processes handled by a remote Supervisor. """
        from supvisors.mainloop import SupvisorsMainLoop
        from supvisors.ttypes import AddressStates
        main_loop = SupvisorsMainLoop(self.supvisors)
        # patch the main loop send_remote_comm_event
        # test the check_address behaviour through the calls to internal events
        with patch.object(main_loop, 'send_remote_comm_event') as mocked_evt:
            # test rpc error: no event is sent to local Supervisor
            self.mocked_rpc.side_effect = Exception
            main_loop.check_address('10.0.0.1')
            self.assertEqual(2, self.mocked_rpc.call_count)
            self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
            self.assertEqual(0, mocked_evt.call_count)
            # test with a mocked rpc interface
            rpc_intf = DummyRpcInterface()
            self.mocked_rpc.side_effect = None
            self.mocked_rpc.return_value = rpc_intf
            self.mocked_rpc.reset_mock()
            # test with address in isolation
            with patch.object(rpc_intf.supervisor, 'getAllProcessInfo') as mocked_supervisor:
                for state in [AddressStates.ISOLATING, AddressStates.ISOLATED]:
                    with patch.object(rpc_intf.supvisors, 'get_address_info', return_value={'statecode': state}):
                        main_loop.check_address('10.0.0.1')
                        self.assertEqual(1, self.mocked_rpc.call_count)
                        self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
                        self.assertEqual(1, mocked_evt.call_count)
                        self.assertEqual(call('auth', 'address_name:10.0.0.1 authorized:False'), mocked_evt.call_args)
                        self.assertEqual(0, mocked_supervisor.call_count)
                        # reset counters
                        mocked_evt.reset_mock()
                        self.mocked_rpc.reset_mock()
            # test with address not in isolation
            with patch.object(rpc_intf.supervisor, 'getAllProcessInfo', return_value=['dummy_list']) as mocked_supervisor:
                for state in [AddressStates.UNKNOWN, AddressStates.CHECKING, AddressStates.RUNNING, AddressStates.SILENT]:
                    with patch.object(rpc_intf.supvisors, 'get_address_info', return_value={'statecode': state}):
                        main_loop.check_address('10.0.0.1')
                        self.assertEqual(1, self.mocked_rpc.call_count)
                        self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
                        self.assertEqual(2, mocked_evt.call_count)
                        self.assertEqual([call('info', '["10.0.0.1", ["dummy_list"]]'),
                            call('auth', 'address_name:10.0.0.1 authorized:True')], mocked_evt.call_args_list)
                        self.assertEqual(1, mocked_supervisor.call_count)
                        # reset counters
                        mocked_evt.reset_mock()
                        mocked_supervisor.reset_mock()
                        self.mocked_rpc.reset_mock()

    def test_start_process(self):
        """ Test the protocol to start a process handled by a remote Supervisor. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # test rpc error
        self.mocked_rpc.side_effect = Exception
        main_loop.start_process('10.0.0.1', 'dummy_process', 'extra args')
        self.assertEqual(2, self.mocked_rpc.call_count)
        self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
        # test with a mocked rpc interface
        rpc_intf = DummyRpcInterface()
        self.mocked_rpc.side_effect = None
        self.mocked_rpc.return_value = rpc_intf
        with patch.object(rpc_intf.supvisors, 'start_args') as mocked_supvisors:
            main_loop.start_process('10.0.0.1', 'dummy_process', 'extra args')
            self.assertEqual(3, self.mocked_rpc.call_count)
            self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
            self.assertEqual(1, mocked_supvisors.call_count)
            self.assertEqual(call('dummy_process', 'extra args', False), mocked_supvisors.call_args)

    def test_stop_process(self):
        """ Test the protocol to stop a process handled by a remote Supervisor. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # test rpc error
        self.mocked_rpc.side_effect = Exception
        main_loop.stop_process('10.0.0.1', 'dummy_process')
        self.assertEqual(2, self.mocked_rpc.call_count)
        self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
        # test with a mocked rpc interface
        rpc_intf = DummyRpcInterface()
        self.mocked_rpc.side_effect = None
        self.mocked_rpc.return_value = rpc_intf
        with patch.object(rpc_intf.supervisor, 'stopProcess') as mocked_supervisor:
            main_loop.stop_process('10.0.0.1', 'dummy_process')
            self.assertEqual(3, self.mocked_rpc.call_count)
            self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
            self.assertEqual(1, mocked_supervisor.call_count)
            self.assertEqual(call('dummy_process', False), mocked_supervisor.call_args)

    def test_restart(self):
        """ Test the protocol to restart a remote Supervisor. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # test rpc error
        self.mocked_rpc.side_effect = Exception
        main_loop.restart('10.0.0.1')
        self.assertEqual(2, self.mocked_rpc.call_count)
        self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
        # test with a mocked rpc interface
        rpc_intf = DummyRpcInterface()
        self.mocked_rpc.side_effect = None
        self.mocked_rpc.return_value = rpc_intf
        with patch.object(rpc_intf.supervisor, 'restart') as mocked_supervisor:
            main_loop.restart('10.0.0.1')
            self.assertEqual(3, self.mocked_rpc.call_count)
            self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
            self.assertEqual(1, mocked_supervisor.call_count)
            self.assertEqual(call(), mocked_supervisor.call_args)

    def test_shutdown(self):
        """ Test the protocol to shutdown a remote Supervisor. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # test rpc error
        self.mocked_rpc.side_effect = Exception
        main_loop.shutdown('10.0.0.1')
        self.assertEqual(2, self.mocked_rpc.call_count)
        self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
        # test with a mocked rpc interface
        rpc_intf = DummyRpcInterface()
        self.mocked_rpc.side_effect = None
        self.mocked_rpc.return_value = rpc_intf
        with patch.object(rpc_intf.supervisor, 'shutdown') as mocked_shutdown:
            main_loop.shutdown('10.0.0.1')
            self.assertEqual(3, self.mocked_rpc.call_count)
            self.assertEqual(call('10.0.0.1', main_loop.env), self.mocked_rpc.call_args)
            self.assertEqual(1, mocked_shutdown.call_count)
            self.assertEqual(call(), mocked_shutdown.call_args)

    def test_comm_event(self):
        """ Test the protocol to send a comm event to the local Supervisor. """
        from supvisors.mainloop import SupvisorsMainLoop
        main_loop = SupvisorsMainLoop(self.supvisors)
        # test rpc error
        with patch.object(main_loop.proxy.supervisor,'sendRemoteCommEvent', side_effect=Exception):
            main_loop.send_remote_comm_event('event type', 'event data')
        # test with a mocked rpc interface
        with patch.object(main_loop.proxy.supervisor,'sendRemoteCommEvent') as mocked_supervisor:
            main_loop.send_remote_comm_event('event type', 'event data')
            self.assertEqual(1, mocked_supervisor.call_count)
            self.assertEqual(call('event type', 'event data'), mocked_supervisor.call_args)

    def check_call(self, main_loop, mocked_loop, method_name, request, args):
        """ Perform a main loop request and check what has been called. """
        # send request
        main_loop.send_request(request, args)
        # test mocked main loop
        for key, mocked in mocked_loop.items():
            if key == method_name:
                self.assertEqual(1, mocked.call_count)
                self.assertEqual(call(*args), mocked.call_args)
                mocked.reset_mock()
            else:
                self.assertEqual(0, mocked.call_count)
        # test mocked subscriber
        if not method_name:
            self.assertEqual(1, main_loop.subscriber.disconnect.call_count)
            self.assertEqual(call(args), main_loop.subscriber.disconnect.call_args)
            main_loop.subscriber.disconnect.reset_mock()
        else:
            self.assertEqual(0, main_loop.subscriber.disconnect.call_count)

    def test_send_request(self):
        """ Test the execution of a deferred Supervisor request. """
        from supvisors.mainloop import SupvisorsMainLoop
        from supvisors.utils import DeferredRequestHeaders
        main_loop = SupvisorsMainLoop(self.supvisors)
        # patch main loop subscriber
        with patch.multiple(main_loop, check_address=DEFAULT,
            start_process=DEFAULT, stop_process=DEFAULT,
            restart=DEFAULT, shutdown=DEFAULT) as mocked_loop:
            # test check address
            self.check_call(main_loop, mocked_loop, 'check_address',
                DeferredRequestHeaders.CHECK_ADDRESS, ('10.0.0.2', ))
            # test isolate addresses
            self.check_call(main_loop, mocked_loop, '',
                DeferredRequestHeaders.ISOLATE_ADDRESSES, ('10.0.0.2', '10.0.0.3'))
            # test start process
            self.check_call(main_loop, mocked_loop, 'start_process',
                DeferredRequestHeaders.START_PROCESS, ('10.0.0.2', 'dummy_process', 'extra args'))
            # test stop process
            self.check_call(main_loop, mocked_loop, 'stop_process',
                DeferredRequestHeaders.STOP_PROCESS, ('10.0.0.2', 'dummy_process'))
            # test restart
            self.check_call(main_loop, mocked_loop, 'restart',
                DeferredRequestHeaders.RESTART, ('10.0.0.2', ))
            # test shutdown
            self.check_call(main_loop, mocked_loop, 'shutdown',
                DeferredRequestHeaders.SHUTDOWN, ('10.0.0.2', ))


def test_suite():
    return unittest.findTestCases(sys.modules[__name__])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
