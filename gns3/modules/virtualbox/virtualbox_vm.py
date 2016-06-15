# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
VirtualBox VM implementation.
"""

import sys
import os
import tempfile

from gns3.node import Node
from gns3.ports.ethernet_port import EthernetPort
from .settings import VBOX_VM_SETTINGS

import logging
log = logging.getLogger(__name__)


class VirtualBoxVM(Node):

    """
    VirtualBox VM.

    :param module: parent module for this node
    :param server: GNS3 server instance
    :param project: Project instance
    """

    URL_PREFIX = "virtualbox"

    def __init__(self, module, server, project):

        super().__init__(module, server, project)
        log.info("VirtualBox VM instance is being created")
        self._linked_clone = False
        self._port_name_format = None
        self._port_segment_size = 0
        self._first_port_name = None

        virtualbox_vm_settings = {"vmname": "",
                                  "console": None,
                                  "console_host": None,
                                  "adapters": VBOX_VM_SETTINGS["adapters"],
                                  "use_any_adapter": VBOX_VM_SETTINGS["use_any_adapter"],
                                  "adapter_type": VBOX_VM_SETTINGS["adapter_type"],
                                  "ram": VBOX_VM_SETTINGS["ram"],
                                  "headless": VBOX_VM_SETTINGS["headless"],
                                  "acpi_shutdown": VBOX_VM_SETTINGS["acpi_shutdown"],
                                  "enable_remote_console": VBOX_VM_SETTINGS["enable_remote_console"]}

        self.settings().update(virtualbox_vm_settings)

    def _addAdapters(self, adapters):
        """
        Adds adapters.

        :param adapters: number of adapters
        """

        interface_number = segment_number = 0
        for adapter_number in range(0, adapters):
            if self._first_port_name and adapter_number == 0:
                port_name = self._first_port_name
            else:
                port_name = self._port_name_format.format(
                    interface_number,
                    segment_number,
                    port0 = interface_number,
                    port1 = 1 + interface_number,
                    segment0 = segment_number,
                    segment1 = 1 + segment_number
                )
                interface_number += 1
                if self._port_segment_size and interface_number % self._port_segment_size == 0:
                    segment_number += 1
                    interface_number = 0
            new_port = EthernetPort(port_name)
            new_port.setAdapterNumber(adapter_number)
            new_port.setPortNumber(0)
            self._ports.append(new_port)
            log.debug("Adapter {} with port {} has been added".format(adapter_number, port_name))

    def create(self, vmname, name=None, node_id=None, port_name_format="Ethernet{0}", port_segment_size=0,
              first_port_name="", linked_clone=False, additional_settings={}, default_name_format=None):
        """
        Creates this VirtualBox VM.

        :param vmname: VM name in VirtualBox
        :param name: optional name
        :param node_id: Node identifier
        :param linked_clone: either the VM is a linked clone
        :param additional_settings: additional settings for this VM
        """

        if not name:
            name = vmname

        self._linked_clone = linked_clone
        params = {"vmname": vmname,
                  "linked_clone": linked_clone}
        self._port_name_format = port_name_format
        self._port_segment_size = port_segment_size
        self._first_port_name = first_port_name
        params.update(additional_settings)
        self._create(name, node_id, params, default_name_format)

    def _createCallback(self, result):
        """
        Callback for create.

        :param result: server response (dict)
        """

        # create the ports on the client side
        self._addAdapters(self._settings.get("adapters", 0))

    def update(self, new_settings):
        """
        Updates the settings for this VirtualBox VM.

        :param new_settings: settings (dict)
        """

        if "name" in new_settings and new_settings["name"] != self.name():
            if self._linked_clone:
                # forces the update of the VM name in VirtualBox.
                new_settings["vmname"] = new_settings["name"]

        params = {}
        for name, value in new_settings.items():
            if name in self._settings and self._settings[name] != value:
                params[name] = value

        if params:
            self._update(params)

    def _updateCallback(self, result):
        """
        Callback for update.

        :param result: server response (dict)
        """

        nb_adapters_changed = False
        for name, value in result.items():
            if name in self._settings and self._settings[name] != value:
                log.info("{}: updating {} from '{}' to '{}'".format(self.name(), name, self._settings[name], value))
                if name == "adapters":
                    nb_adapters_changed = True
                self._settings[name] = value

        if nb_adapters_changed:
            log.debug("number of adapters has changed to {}".format(self._settings["adapters"]))
            # TODO: dynamically add/remove adapters
            self._ports.clear()
            self._addAdapters(self._settings["adapters"])

    def info(self):
        """
        Returns information about this VirtualBox VM instance.

        :returns: formated string
        """

        if self.status() == Node.started:
            state = "started"
        else:
            state = "stopped"

        info = """VirtualBox VM {name} is {state}
  Local node ID is {id}
  Server's node ID is {node_id}
  VirtualBox name is "{vmname}"
  RAM is {ram} MB
  VirtualBox VM's server runs on {host}, console is on port {console}
""".format(name=self.name(),
           id=self.id(),
           node_id=self._node_id,
           state=state,
           vmname=self._settings["vmname"],
           ram=self._settings["ram"],
           host=self.compute().id(),
           console=self._settings["console"])

        port_info = ""
        for port in self._ports:
            if port.isFree():
                port_info += "     {port_name} is empty\n".format(port_name=port.name())
            else:
                port_info += "     {port_name} {port_description}\n".format(port_name=port.name(),
                                                                            port_description=port.description())

        return info + port_info

    def dump(self):
        """
        Returns a representation of this VirtualBox VM instance.
        (to be saved in a topology file).

        :returns: representation of the node (dictionary)
        """

        vbox_vm = super().dump()
        vbox_vm["linked_clone"] = self._linked_clone
        vbox_vm["port_name_format"] = self._port_name_format

        if self._port_segment_size:
            vbox_vm["port_segment_size"] = self._port_segment_size
        if self._first_port_name:
            vbox_vm["first_port_name"] = self._first_port_name

        # add the properties
        for name, value in self._settings.items():
            if value is not None and value != "":
                vbox_vm["properties"][name] = value

        return vbox_vm

    def load(self, node_info):
        """
        Loads a VirtualBox VM representation
        (from a topology file).

        :param node_info: representation of the node (dictionary)
        """

        super().load(node_info)

        # for backward compatibility
        node_id = node_info.get("vbox_id")
        if not node_id:
            node_id = node_info.get("node_id")
            if not node_id:
                node_id = node_info.get("vm_id")

        linked_clone = node_info.get("linked_clone", False)
        port_name_format = node_info.get("port_name_format", "Ethernet{0}")
        port_segment_size = node_info.get("port_segment_size", 0)
        first_port_name = node_info.get("first_port_name", "")

        vm_settings = {}
        for name, value in node_info["properties"].items():
            if name in self._settings:
                vm_settings[name] = value
        vm_settings["adapters"] = vm_settings.get("adapters", 1)  # for compatibility
        name = vm_settings.pop("name")
        vmname = vm_settings.pop("vmname")

        log.info("VirtualBox VM {} is loading".format(name))
        self.create(vmname, name, node_id, port_name_format, port_segment_size, first_port_name, linked_clone, vm_settings)

    def serialConsole(self):
        """
        Returns either the serial console must be used or not.

        :return: boolean
        """

        if self._settings["enable_remote_console"]:
            return False
        return True

    def serialPipe(self):
        """
        Returns the VM serial pipe path for serial console connections.

        :returns: path to the serial pipe
        """

        if sys.platform.startswith("win"):
            pipe_name = r"\\.\pipe\gns3_vbox\{}".format(self._node_id)
        else:
            pipe_name = os.path.join(tempfile.gettempdir(), "gns3_vbox", "{}".format(self._node_id))
            os.makedirs(os.path.dirname(pipe_name), exist_ok=True)
        return pipe_name

    def console(self):
        """
        Returns the console port for this VirtualBox VM instance.

        :returns: port (integer)
        """
        return self._settings["console"]

    def configPage(self):
        """
        Returns the configuration page widget to be used by the node properties dialog.

        :returns: QWidget object
        """

        from .pages.virtualbox_vm_configuration_page import VirtualBoxVMConfigurationPage
        return VirtualBoxVMConfigurationPage

    @staticmethod
    def defaultSymbol():
        """
        Returns the default symbol path for this node.

        :returns: symbol path (or resource).
        """

        return ":/symbols/vbox_guest.svg"

    @staticmethod
    def symbolName():

        return "VirtualBox VM"

    @staticmethod
    def categories():
        """
        Returns the node categories the node is part of (used by the device panel).

        :returns: list of node categories
        """

        return [Node.end_devices]

    def __str__(self):

        return "VirtualBox VM"
