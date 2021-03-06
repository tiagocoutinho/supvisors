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

from time import ctime

# gravity classes for _messages
# use of 'erro' instead of 'error' in order to avoid HTTP error log traces
Info ='info'
Warn = 'warn'
Error = 'erro'

def format_gravity_message(message):
    if not isinstance(message, tuple):
        # gravity is not set by Supervisor so let's deduce it
        if 'ERROR' in message:
            message = message.replace('ERROR: ', '')
            gravity = Error
        else:
            gravity = Info
        return gravity, message
    return message

def print_message(root, gravity, message):
    # print _message as a result of action
    elt = root.findmeld('message_mid')
    if message is not None:
        elt.attrib['class'] = gravity
        elt.content(message)
    else:
        elt.attrib['class'] = 'empty'
        elt.content('')

def info_message(msg, address=None):
    return Info, msg + ' at {}'.format(ctime()) + (' on {}'.format(address) if address else '')

def warn_message(msg, address=None):
    return Warn, msg + ' at {}'.format(ctime()) + (' on {}'.format(address) if address else '')

def error_message(msg, address=None):
    return Error, msg + ' at {}'.format(ctime()) + (' on {}'.format(address) if address else '')

def delayed_info(msg, address=None):
    def on_wait():
        return info_message(msg, address)
    on_wait.delay = 0.05
    return on_wait

def delayed_warn(msg, address=None):
    def on_wait():
        return warn_message(msg, address)
    on_wait.delay = 0.05
    return on_wait

def delayed_error(msg, address=None):
    def on_wait():
        return error_message(msg, address)
    on_wait.delay = 0.05
    return on_wait

