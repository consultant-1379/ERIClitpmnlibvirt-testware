"""
COPYRIGHT Ericsson 2019
The copyright to the computer program(s) herein is the property of
Ericsson Inc. The programs may be used and/or copied only with written
permission from Ericsson Inc. or in accordance with the terms and
conditions stipulated in the agreement/contract under which the
program(s) have been supplied.

@since:     Jan 2015
@author:    Philip Daly
@summary:   As a LITP User I want the libvirt adaptor to check the internal
            status of the VM so that application faults can be detected.
            Agile: LITPCDS-7535
"""

from litp_generic_test import GenericTest, attr
from redhat_cmd_utils import RHCmdUtils
from libvirt_utils import LibvirtUtils
import test_constants
from json_utils import JSONUtils
from networking_utils import NetworkingUtils
from vcs_utils import VCSUtils
import os


class Story7535(GenericTest):
    """
    LITPCDS-7535:
    As a LITP User I want the libvirt adaptor to check the internal
    status of the VM so that application faults can be detected.
    """

    def setUp(self):
        """
        Description:
            Runs before every single test
        Actions:
            Determine
                management server,
                primary vcs node(first node in array
                                 returned from test framework)
                list of all managed nodes
        Results:
            Class variables that are required to execute tests
        """
        # 1. Call super class setup
        super(Story7535, self).setUp()
        self.litp_port = "9999"
        self.rh_os = RHCmdUtils()
        self.libvirt = LibvirtUtils()
        self.net_utils = NetworkingUtils()
        self.temp_image = "rhel.img"
        self.temp_invalid_image_503 = "rhelinvalid503.img"
        self.temp_invalid_image_400 = "rhelinvalid400.img"
        self.rhel7_4_image = "rhel7_4.img"
        self.invalid_rhel7_4_image_400 = "rhel7_4invalid400.img"
        self.json_utils = JSONUtils()
        self.adaptor_pkg_name = test_constants.LIBVIRT_ADAPTOR_PKG_NAME
        self.libvirt_dir = test_constants.LIBVIRT_DIR
        self.temp_image_location = test_constants.VM_IMAGE_MS_DIR
        self.instances_data_dir = test_constants.LIBVIRT_INSTANCES_DIR
        self.images_dir = test_constants.LIBVIRT_IMAGE_DIR
        self.management_server = self.get_management_node_filename()
        self.list_managed_nodes = self.get_managed_node_filenames()
        self.primary_node = self.list_managed_nodes[0]
        self.vcs = VCSUtils()
        # Location where the RPMs to be used are stored
        self.rpm_src_dir = \
            os.path.dirname(os.path.realpath(__file__)) + "/rpms"

        # CHECK WHETHER THE IMG IS IN THE TMP DIR ON THE NODE - IF NOT COPY
        dir_contents = \
        self.list_dir_contents(self.primary_node,
                               '/tmp')
        if self.temp_image not in dir_contents:
            self.wget_image_to_node(self.management_server, self.primary_node,
                                    "vm_test_image-2-1.0.8.qcow2", '/tmp',
                                    self.temp_image)

        if self.temp_invalid_image_400 not in dir_contents:
            self.wget_image_to_node(self.management_server, self.primary_node,
                                    'vm_test_image_neg-1-1.0.7.qcow2', '/tmp',
                                    self.temp_invalid_image_400)

        if self.temp_invalid_image_503 not in dir_contents:
            self.wget_image_to_node(self.management_server, self.primary_node,
                                    'vm_test_image_neg-2-1.0.7.qcow2', '/tmp',
                                    self.temp_invalid_image_503)

        # TORF-271798: RHEL7.4 images
        rhel7_4_img_dict = \
            {self.rhel7_4_image: "vm_test_image-5-1.0.7.qcow2",
             self.invalid_rhel7_4_image_400: "vm_test_image_neg-3-1.0.6.qcow2"}
        for img_name, img_url in rhel7_4_img_dict.items():
            if img_name not in dir_contents:
                self.wget_image_to_node(self.management_server,
                                        self.primary_node,
                                        img_url, '/tmp', img_name)

    def tearDown(self):
        """
        Description:
            Runs after every single test
        Actions:
            -
        Results:
            The super class prints out diagnostics and variables
        """
        super(Story7535, self).tearDown()

    @staticmethod
    def get_virsh_destroy_cmd(vm_name):
        """
        Function to return the virsh command needed to destroy the provided
        virtual machine.

        Args:
            vm_name (str): The name of the virtual machine, as it appears in
                           the virsh console, which is to be destroyed.


        Return:
            str. The destroy command to be issued against the virtual machine.
        """

        return "/usr/bin/virsh destroy {0}".format(vm_name)

    def chk_dependencies_installed(self):
        """
        CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
        INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
        """
        installed_libvirt = False
        adaptor_installed = False
        # checking the status of libvirtd returns 1 if the service is
        # unrecognised and 3 if the service is stopped
        virsh_cmd = self.rh_os.get_systemctl_status_cmd('libvirtd')
        _, _, return_code = \
            self.run_command(self.primary_node, virsh_cmd, su_root=True)
        if return_code != 0:
            libvirt_install_cmd = \
                self.rhc.get_yum_install_cmd(["libvirt"])
            _, _, return_code = \
                self.run_command(self.primary_node, libvirt_install_cmd,
                                 su_root=True)

            self.assertEqual(0, return_code)
            installed_libvirt = True

            start_libvirt_cmd = self.rh_os.get_systemctl_start_cmd('libvirtd')
            _, _, return_code = \
                self.run_command(self.primary_node,
                                 start_libvirt_cmd, su_root=True)
            self.assertEqual(0, return_code)

        installed_cmd = \
            self.rh_os.check_pkg_installed([self.adaptor_pkg_name])
        _, _, return_code = \
            self.run_command(self.primary_node, installed_cmd, su_root=True)
        if return_code != 0:
            adaptor_installed = True
            self.install_rpm_on_node(self.primary_node,
                                     test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

        return installed_libvirt, adaptor_installed

    def copy_image_to_node(self, image_name, app_data_dir):
        """
        Copy the image to the correct location on the node

        Create the instance directory and the test application subdirectory
        """
        dir_contents = \
            self.list_dir_contents(self.primary_node, self.libvirt_dir)
        image_dir_name = self.images_dir.split('/')[-1]
        if image_dir_name not in dir_contents:
            self.create_dir_on_node(self.primary_node,
                                    self.images_dir,
                                    su_root=True)
        self.cp_file_on_node(self.primary_node,
                             '/tmp/{0}'.format(image_name),
                             test_constants.LIBVIRT_IMAGE_DIR +
                             '/{0}'.format(image_name),
                             su_root=True)

        instances_dir_name = self.instances_data_dir.split('/')[-1]
        if instances_dir_name not in dir_contents:
            self.create_dir_on_node(self.primary_node,
                                    self.instances_data_dir,
                                    su_root=True)
        self.create_dir_on_node(self.primary_node,
                                app_data_dir,
                                su_root=True)

    def cleanup_after_test(self, vm_service_name,
                           installed_libvirt, adaptor_installed):
        """
        Remove images
        undefine service in virsh
        Uninstall libvirt and the adaptor if they were installed by
        these test cases
        """
        self.remove_item(self.primary_node, self.images_dir +
                         '/{0}'.format(self.temp_image),
                         su_root=True)
        self.remove_item(self.primary_node, self.images_dir +
                         '/{0}'.format(self.temp_invalid_image_503),
                         su_root=True)
        self.remove_item(self.primary_node, self.images_dir +
                         '/{0}'.format(self.temp_invalid_image_400),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '{0}/{1}'.format(self.images_dir, self.rhel7_4_image),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '{0}/{1}'.format(self.images_dir,
                                          self.invalid_rhel7_4_image_400),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '/tmp/{0}'.format(self.temp_image),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '/tmp/{0}'.format(self.temp_invalid_image_503),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '/tmp/{0}'.format(self.temp_invalid_image_400),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '/tmp/{0}'.format(self.rhel7_4_image),
                         su_root=True)
        self.remove_item(self.primary_node, '/tmp/{0}'.
                         format(self.invalid_rhel7_4_image_400),
                         su_root=True)
        vm_destroy_cmd = \
            self.get_virsh_destroy_cmd(vm_service_name)
        self.run_command(self.primary_node, vm_destroy_cmd, su_root=True)

        vm_undefine_cmd = \
            self.libvirt.get_virsh_undefine_cmd(vm_service_name)
        self.run_command(self.primary_node, vm_undefine_cmd, su_root=True)

        if installed_libvirt:
            cmd = self.rhc.get_yum_remove_cmd(["libvirt"])
            self.run_command(self.primary_node, cmd, su_root=True)
        if adaptor_installed:
            self.remove_rpm_on_node(self.primary_node,
                                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

    def get_bridge_urls(self):
        """
        return a list of Bridge URLs from the managed node
        """
        node_url = \
            self.get_node_url_from_filename(self.management_server,
                                            self.primary_node)

        bridge_urls = self.find(self.management_server,
                                node_url, "bridge")
        return bridge_urls

    def get_bridge_details(self, bridge_urls):
        """
        return dictionary of bridged interfaces defined in the model
        on the node and their IP address
        """
        self.assertNotEqual([], bridge_urls)
        bridges = {}
        for bridge_url in bridge_urls:
            bridge_name = \
                self.get_props_from_url(self.management_server, bridge_url,
                                        "device_name")
            net_name = \
                self.get_props_from_url(self.management_server, bridge_url,
                                        "network_name")
            free_ipaddress = \
                self.get_free_ip_by_net_name(self.management_server, net_name)
            bridges[bridge_name] = free_ipaddress
        return bridges

    def prepare_metadata_content(self, bridge_urls, check_ipaddress):
        """
        prepare content of metadata file
        """
        network_name = \
            self.get_props_from_url(self.management_server, bridge_urls[0],
                                    "network_name")
        bridge_name = \
            self.get_props_from_url(self.management_server, bridge_urls[0],
                                    "device_name")
        ifconfig_cmd = \
            self.net_utils.get_ifconfig_cmd(bridge_name)
        stdout, _, _ = \
            self.run_command(self.primary_node,
                             ifconfig_cmd, su_root=True)
        split_address = check_ipaddress.split('.')
        broadcast = \
            "{0}.{1}.{2}.255".format(split_address[0], split_address[1],
                                     split_address[2])
        gateway = \
            "{0}.{1}.{2}.1".format(split_address[0], split_address[1],
                                   split_address[2])
        ifconfig_dict = self.net_utils.get_ifcfg_dict(stdout, bridge_name)
        netmask = ifconfig_dict['MASK']
        meta_data_content = \
            ["instance-id: service_name",
             "local-hostname: vm-service-host",
             "network-interfaces: \"iface eth0 inet static",
             "",
             "address {0}".format(check_ipaddress),
             "",
             "network {0}".format(network_name),
             "",
             "netmask {0}".format(netmask),
             "",
             "broadcast {0}".format(broadcast),
             "",
             "gateway {0}".format(gateway),
             "",
             "\""]
        return meta_data_content

    def prepare_network_config_content(self, bridge_url, check_ipaddress):
        """
        prepare content of network-config file
        Args:
            bridge_url: (str) A bridge device URL in the litp model
            check_ipaddress: (str) An ip address of a bridge device in a model
        Returns:
            Structured network-config file content
        """
        bridge_name = \
            self.get_props_from_url(self.management_server, bridge_url,
                                    "device_name")
        ifconfig_cmd = \
            self.net_utils.get_ifconfig_cmd(bridge_name)
        ifconfig_output, _, _ = \
            self.run_command(self.primary_node,
                             ifconfig_cmd, su_root=True)
        split_address = check_ipaddress.split('.')
        gateway = \
            "{0}.{1}.{2}.1".format(split_address[0], split_address[1],
                                   split_address[2])
        ifconfig_dict = self.net_utils.get_ifcfg_dict(ifconfig_output,
                                                      bridge_name)
        netmask = ifconfig_dict['MASK']
        mac_address = '52:54:00:67:28:80'
        network_config_content = \
            ["config:",
             "- mac_address: {0}".format(mac_address),
             "  name: eth0",
             "  subnets:",
             "  - address: {0}".format(check_ipaddress),
             "    gateway: {0}".format(gateway),
             "    netmask: {0}".format(netmask),
             "    type: static",
             "  type: physical",
             "version: 1"]
        return network_config_content

    def wait_for_vm_start(self, vm_service_name):
        """
        wait for virtual machine to completely start.
        Check by connecting to the virtual machine using virsh console.
        """
        expected_stdout = 'vm-service-host.localdomain login:'
        self.wait_for_cmd(self.primary_node,
                          "virsh console {0}".format(vm_service_name),
                          -1,
                          expected_stdout=expected_stdout,
                          su_root=True)

    @attr('all', 'revert', 'story7535', 'story7535_tc01', 'torf271798')
    def test_01_p_vm_positive_check_on(self):
        """
        Description:
            To ensure that it is possible to status check a successfully
            deployed vm and receive a positive value of 200 in response,
            which indicates a status OK when the internal_status_check
            flag has been set to true.
            TORF-271798: verification of a RHEL7.4 based vm service

        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop command.

        Results:
            The vm is deployed successfully, successfully cycles through
            the commands issued against it
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp7535_0"
        this_app_data_dir = '{0}/{1}/'.format(self.instances_data_dir,
                                              vm_service_name)

        try:
            # STEP 1
            installed_libvirt, adaptor_installed =\
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image,
                                    this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()

            loaded_file = self.json_utils.load_json(config_file_dump)

            bridge_urls = self.get_bridge_urls()
            bridges = self.get_bridge_details(bridge_urls)

            interfaces_dict = {}
            counter = 0
            for bridge in bridges.keys():
                interfaces_dict["eth{0}".format(counter)] = \
                {"host_device": bridge, "ipaddress": bridges[bridge]}
                counter += 1
            loaded_file["vm_data"]["interfaces"] = interfaces_dict
            loaded_file["adaptor_data"]["status-retry"] = 600
            loaded_file["adaptor_data"]["status-timeout"] = 600
            loaded_file["adaptor_data"]["start-timeout"] = 600
            loaded_file["adaptor_data"]["internal_status_check"] = {}
            loaded_file["adaptor_data"]["internal_status_check"]["active"] = \
            'on'
            check_ipaddress = interfaces_dict['eth0']['ipaddress']
            loaded_file["adaptor_data"]["internal_"
                                        "status_check"]["ip_address"] = \
                                        check_ipaddress
            config_file_dump = self.json_utils.dump_json(loaded_file)

            self.create_file_on_node(self.primary_node, this_app_data_dir +
                                     '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            meta_data_content = self.prepare_metadata_content(bridge_urls,
                                                              check_ipaddress)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name,
                                                            meta_data_content)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop')

            # TORF-271798: verification of a RHEL7.4 based vm service
            # Remove old config.json, to be replaced with new config.json
            # containing rhel7.4 image and mac address
            self.remove_item(self.primary_node, this_app_data_dir +
                             'config.json', su_root=True)
            interfaces_dict = {}
            mac_add = '52:54:00:67:28:80'
            interfaces_dict["eth0"] = {"host_device": bridges.keys()[0],
                                       "ipaddress": bridges.values()[0],
                                       "mac_address": mac_add}
            loaded_file["vm_data"]["interfaces"] = interfaces_dict
            loaded_file["vm_data"]["image"] = self.rhel7_4_image

            config_file_dump = self.json_utils.dump_json(loaded_file)
            self.create_file_on_node(self.primary_node, this_app_data_dir +
                                     '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            self.cp_file_on_node(self.primary_node,
                                 '/tmp/{0}'.format(self.rhel7_4_image),
                                 test_constants.LIBVIRT_IMAGE_DIR +
                                 '/{0}'.format(self.rhel7_4_image),
                                 su_root=True)

            network_config_path = this_app_data_dir + '/network-config'
            network_config_content = self.prepare_network_config_content(
                bridge_urls[0], check_ipaddress)
            self.remove_item(self.primary_node, network_config_path,
                             su_root=True)
            self.create_file_on_node(self.primary_node, network_config_path,
                                     network_config_content, su_root=True)

            vm_service_cmd = ['start', 'status', 'stop']
            for cmd in vm_service_cmd:
                self.run_libvirt_service_cmd(self.primary_node,
                                             vm_service_name, cmd)
        finally:
            self.cleanup_after_test(vm_service_name,
                                    installed_libvirt,
                                    adaptor_installed)

    @attr('all', 'revert', 'story7535', 'story7535_tc02')
    def test_02_n_vm_negative_check_on(self):
        """
        Description:
            To ensure that it is possible to status check a deployed vm which
            has been configured to return a failure on status check and receive
            a non 200 value in response, which indiates a status NOT OK when
            the internal_status_check flag has been set to true

        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop command.

        Results:
            The vm is deployed successfully, successfully cycles through
            the commands issued against it
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp7535_1"
        this_app_data_dir = \
        self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # STEP 1
            installed_libvirt, adaptor_installed =\
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_invalid_image_503,
                                    this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()

            loaded_file = self.json_utils.load_json(config_file_dump)

            bridge_urls = self.get_bridge_urls()
            bridges = self.get_bridge_details(bridge_urls)

            interfaces_dict = {}
            counter = 0
            for bridge in bridges.keys():
                interfaces_dict["eth{0}".format(counter)] = \
                {"host_device": bridge, "ipaddress": bridges[bridge]}
                counter += 1
            loaded_file["vm_data"]["interfaces"] = interfaces_dict
            loaded_file["vm_data"]["image"] = self.temp_invalid_image_503
            loaded_file["adaptor_data"]["status-retry"] = 600
            loaded_file["adaptor_data"]["status-timeout"] = 600
            loaded_file["adaptor_data"]["start-timeout"] = 600
            loaded_file["adaptor_data"]["internal_status_check"] = {}
            loaded_file["adaptor_data"]["internal_status_check"]["active"] = \
            'on'
            check_ipaddress = interfaces_dict['eth0']['ipaddress']
            loaded_file["adaptor_data"]["internal_"
                                        "status_check"]["ip_address"] = \
                                        check_ipaddress
            config_file_dump = self.json_utils.dump_json(loaded_file)

            self.create_file_on_node(self.primary_node, this_app_data_dir +
                                     '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            meta_data_content = self.prepare_metadata_content(bridge_urls,
                                                              check_ipaddress)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name,
                                                            meta_data_content)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start', expect_positive=False,
                                         timeout=60)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status', expect_positive=False)

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop')
        finally:
            self.cleanup_after_test(vm_service_name,
                                    installed_libvirt,
                                    adaptor_installed)

    @attr('all', 'revert', 'story7535', 'story7535_tc03')
    def test_03_n_vm_negative_check_off(self):
        """
        Description:
            To ensure that it is possible to check the status of a vm by simply
            verifying the running status of the vm as opposed to the return
            value from the vm - done by setting the internal_status_check
            flag to be false.

        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop command.

        Results:
            The vm is deployed successfully, successfully cycles through
            the commands issued against it
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp7535_2"
        this_app_data_dir = \
        self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # STEP 1
            installed_libvirt, adaptor_installed =\
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_invalid_image_503,
                                    this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()

            loaded_file = self.json_utils.load_json(config_file_dump)

            bridge_urls = self.get_bridge_urls()
            bridges = self.get_bridge_details(bridge_urls)

            interfaces_dict = {}
            counter = 0
            for bridge in bridges.keys():
                interfaces_dict["eth{0}".format(counter)] = \
                {"host_device": bridge, "ipaddress": bridges[bridge]}
                counter += 1
            loaded_file["vm_data"]["interfaces"] = interfaces_dict
            loaded_file["vm_data"]["image"] = self.temp_invalid_image_503
            loaded_file["adaptor_data"]["internal_status_check"] = {}
            loaded_file["adaptor_data"]["internal_status_check"]["active"] = \
            'off'
            check_ipaddress = interfaces_dict['eth0']['ipaddress']
            loaded_file["adaptor_data"]["internal_"
                                        "status_check"]["ip_address"] = \
                                        check_ipaddress
            config_file_dump = self.json_utils.dump_json(loaded_file)

            self.create_file_on_node(self.primary_node, this_app_data_dir +
                                     '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            meta_data_content = self.prepare_metadata_content(bridge_urls,
                                                              check_ipaddress)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name,
                                                            meta_data_content)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop')
        finally:
            self.cleanup_after_test(vm_service_name,
                                    installed_libvirt,
                                    adaptor_installed)

    @attr('all', 'revert', 'story7535', 'story7535_tc04', 'torf271798')
    def test_04_n_vm_negative_check_timeout(self):
        """
        Description:
            To ensure that it is possible to check the status of a vm by simply
            verifying the running status of the vm as opposed to the return
            value from the vm - done by setting the internal_status_check
            flag to be false.
            TORF-271798: verification of a RHEL7.4 based vm service

        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. issue the service <vm_name> stop command.

        Results:
            The adaptor should not receive an expected response of 200
            for success or 503 for failure so it should continue to
            poll for a response. So the start command should timeout.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp7535_3"
        this_app_data_dir = '{0}/{1}/'.format(self.instances_data_dir,
                                              vm_service_name)

        try:
            # STEP 1
            installed_libvirt, adaptor_installed =\
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_invalid_image_400,
                                    this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()

            loaded_file = self.json_utils.load_json(config_file_dump)

            bridge_urls = self.get_bridge_urls()
            bridges = self.get_bridge_details(bridge_urls)

            interfaces_dict = {}
            counter = 0
            for bridge in bridges.keys():
                interfaces_dict["eth{0}".format(counter)] = \
                {"host_device": bridge, "ipaddress": bridges[bridge]}
                counter += 1
            loaded_file["vm_data"]["interfaces"] = interfaces_dict
            loaded_file["vm_data"]["image"] = self.temp_invalid_image_400
            loaded_file["adaptor_data"]["internal_status_check"] = {}
            loaded_file["adaptor_data"]["internal_status_check"]["active"] = \
            'on'
            check_ipaddress = interfaces_dict['eth0']['ipaddress']
            loaded_file["adaptor_data"]["internal_"
                                        "status_check"]["ip_address"] = \
                                        check_ipaddress
            config_file_dump = self.json_utils.dump_json(loaded_file)

            self.create_file_on_node(self.primary_node, this_app_data_dir +
                                     '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            meta_data_content = self.prepare_metadata_content(bridge_urls,
                                                              check_ipaddress)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name,
                                                            meta_data_content)

            # STEP 4
            _, _, ret_code = self.run_libvirt_service_cmd(
                self.primary_node,
                vm_service_name,
                'start',
                expect_positive=False,
                timeout=300)
            self.assertEquals(-1, ret_code)

            self.wait_for_vm_start(vm_service_name)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node,
                                         vm_service_name,
                                         'stop')

            # TORF-271798: verification of a RHEL7.4 based vm service
            # Remove old config.json, to be replaced with new config.json
            # containing invalid rhel7.4 image and mac address
            self.remove_item(self.primary_node, this_app_data_dir +
                             'config.json', su_root=True)
            interfaces_dict = {}
            mac_add = '52:54:00:67:28:80'
            interfaces_dict["eth0"] = {"host_device": bridges.keys()[0],
                                       "ipaddress": bridges.values()[0],
                                       "mac_address": mac_add}
            loaded_file["vm_data"]["interfaces"] = interfaces_dict
            loaded_file["vm_data"]["image"] = self.invalid_rhel7_4_image_400

            config_file_dump = self.json_utils.dump_json(loaded_file)
            self.create_file_on_node(self.primary_node, '{0}config.json'.
                                     format(this_app_data_dir),
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            self.cp_file_on_node(self.primary_node, '/tmp/{0}'.format(
                self.invalid_rhel7_4_image_400), '{0}/{1}'.format(
                    test_constants.LIBVIRT_IMAGE_DIR,
                    self.invalid_rhel7_4_image_400), su_root=True)

            network_config_path = \
                '{0}network-config'.format(this_app_data_dir)
            network_config_content = self.prepare_network_config_content(
                bridge_urls[0], check_ipaddress)
            self.remove_item(self.primary_node, network_config_path,
                             su_root=True)
            self.create_file_on_node(self.primary_node, network_config_path,
                                     network_config_content, su_root=True)

            _, _, ret_code = \
                self.run_libvirt_service_cmd(self.primary_node,
                                             vm_service_name, 'start',
                                             expect_positive=False,
                                             timeout=300)
            self.assertEquals(-1, ret_code)
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status', expect_positive=False)
            self.run_libvirt_service_cmd(self.primary_node,
                                         vm_service_name,
                                         'stop')

        finally:
            self.cleanup_after_test(vm_service_name,
                                    installed_libvirt,
                                    adaptor_installed)
