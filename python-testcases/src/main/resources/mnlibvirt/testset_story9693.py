"""
COPYRIGHT Ericsson 2019
The copyright to the computer program(s) herein is the property of
Ericsson Inc. The programs may be used and/or copied only with written
permission from Ericsson Inc. or in accordance with the terms and
conditions stipulated in the agreement/contract under which the
program(s) have been supplied.

@since:     July 2015
@author:    Stefan
@summary:   As an application designer I want a means of destroying a
            VM following a failed clean up attempt so that my
            application can recover from a failure.
            Agile: LITPCDS-9693
"""

from litp_generic_test import GenericTest, attr
from redhat_cmd_utils import RHCmdUtils
from libvirt_utils import LibvirtUtils
from vcs_utils import VCSUtils
import test_constants
from json_utils import JSONUtils
from networking_utils import NetworkingUtils


class Story9693(GenericTest):
    """
    LITPCDS-9693:
    As an application designer I want a means of destroying a VM
    following a failed clean up attempt so that my application can
    recover from a failure
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
        super(Story9693, self).setUp()
        self.rhc = RHCmdUtils()
        self.libvirt = LibvirtUtils()
        self.vcs = VCSUtils()
        self.json_utils = JSONUtils()
        self.net_utils = NetworkingUtils()
        self.temp_image_name = "rhel.img"
        self.cs_name = "CS_VM2"
        self.libvirt_dir = test_constants.LIBVIRT_DIR
        self.instances_data_dir = test_constants.LIBVIRT_INSTANCES_DIR
        self.images_dir = test_constants.LIBVIRT_IMAGE_DIR
        self.management_server = self.get_management_node_filename()
        self.primary_node = self.get_managed_node_filenames()[0]
        self.primary_node_url = self.get_node_url_from_filename(
            self.management_server, self.primary_node)

        # CHECK WHETHER THE IMG IS IN THE TMP DIR ON THE NODE - IF NOT COPY
        dir_contents = self.list_dir_contents(self.primary_node, '/tmp')
        self.ms_hostname = self.get_node_att(self.management_server,
                                             "hostname")
        sfs_filenames = self.get_sfs_node_filenames()
        self.sfs_hostname = self.get_node_att(sfs_filenames[0],
                                              "hostname")
        self.sfs_ip = self.get_node_att(sfs_filenames[0], "ipv4")
        if self.temp_image_name not in dir_contents:
            ms_dir_contents = \
                self.list_dir_contents(self.management_server,
                                       test_constants.VM_IMAGE_MS_DIR)
            self.wget_image_to_node(self.management_server,
                                    self.primary_node,
                                    ms_dir_contents[0], '/tmp',
                                    self.temp_image_name)

        #Executes cli to find the SFS service,virtual server and sfs pool
        self.pool_url = self.find(self.management_server,
                                  "/infrastructure", "sfs-pool",
                                  assert_not_empty=False)[0]

        self.vcs_cluster_url = self.find(self.management_server,
                                         "/deployments",
                                         "vcs-cluster")[-1]

    def tearDown(self):
        """
        Description:
            Runs after every single test
        Actions:
            -
        Results:
            The super class prints out diagnostics and variables
        """
        super(Story9693, self).tearDown()

    def wait_for_vm_start(self, vm_service_name, node,
                          vm_hostname='vm-service-host.localdomain'):
        """
        wait for virtual machine to completely start.
        Check by connecting to the virtual machine using virsh console.
        """
        expected_stdout = '{0} login:'.format(vm_hostname)
        self.wait_for_cmd(node,
                          "virsh console {0}".format(vm_service_name),
                          -1,
                          expected_stdout=expected_stdout,
                          su_root=True)

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

    def copy_image_to_node(self, image_name, app_data_dir):
        """
        Copy the image to the correct location on the node

        Create the instance directory and the test application
        subdirectory
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

    def chk_dependencies_installed(self):
        """
        CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
        INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
        """
        installed_libvirt = False
        adaptor_installed = False
        # checking the status of libvirtd returns 1 if the service is
        # unrecognised and 3 if the service is stopped
        virsh_cmd = self.rhc.get_systemctl_status_cmd('libvirtd')
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

            start_libvirt_cmd = self.rhc.get_systemctl_start_cmd('libvirtd')
            _, _, return_code = \
                self.run_command(self.primary_node,
                                 start_libvirt_cmd, su_root=True)
            self.assertEqual(0, return_code)

        installed_cmd = self.rhc.check_pkg_installed(
            [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
        _, _, return_code = \
            self.run_command(self.primary_node, installed_cmd, su_root=True)
        if return_code != 0:
            adaptor_installed = True
            self.install_rpm_on_node(self.primary_node,
                                     test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

        return installed_libvirt, adaptor_installed

    def cleanup_after_test(self, vm_service_name,
                           installed_libvirt, adaptor_installed):
        """
        Remove images
        undefine service in virsh
        Uninstall libvirt and the adaptor if they were installed by
        these test cases
        """
        self.remove_item(self.primary_node, self.images_dir +
                         '/{0}'.format(self.temp_image_name),
                         su_root=True)
        self.remove_item(self.primary_node,
                         '/tmp/{0}'.format(self.temp_image_name),
                         su_root=True)
        vm_destroy_cmd = \
            self.libvirt.get_virsh_destroy_cmd(vm_service_name)
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

    def generate_ip_address(self, config):
        """
        Generate IP address
            - find the management network and get the name of the
              network
            - get list of all available IP addresses using the method
              get_free_ip_by_net_name
            - calculate the number of IP addresses required by the
              vm-service instances by adding the active count of each
              clustered service in the config
            - allocate active_count number of IPs from available list
              to each network

        Args:
            config (dict): configuration details for clustered-services

        Returns: -
            net_ip_addresses (dict): Dictionary with keys for each
                network interface, values are list of available IP
                addresses on the management network
        """
        mgmt_network_name = self.get_management_network_name(
            self.management_server)
        self.assertTrue(mgmt_network_name)

        ifree_ip_addresses = self.get_free_ip_by_net_name(
            self.management_server, mgmt_network_name, full_list=True)
        total_nr_of_req_ips = 0
        for clustered_service in config['nodes_per_cs']:
            total_nr_of_req_ips = (
                len(config['interfaces_per_cs'][clustered_service]) * \
                config['params_per_cs'][clustered_service]['active']) + \
                total_nr_of_req_ips

        self.assertTrue(len(ifree_ip_addresses) >= total_nr_of_req_ips)
        net_ip_addresses = {}

        free_ip_index = 0
        for clustered_service in config['interfaces_per_cs']:
            for interface in config['interfaces_per_cs'][clustered_service]:
                if 'dhcp' in interface:
                    net_ip_addresses[interface] = 'ipaddresses=dhcp'
                else:
                    active_cnt = int(
                        config['params_per_cs'][clustered_service]['active'])
                    option_array = []
                    for _ in range(0, active_cnt):
                        option_array.append(ifree_ip_addresses[free_ip_index])
                        free_ip_index = free_ip_index + 1
                    option = ','.join(option_array)
                    net_ip_addresses[interface] = 'ipaddresses=' + option

        return net_ip_addresses

    def get_bridge_info_for_mgmt_network(self):
        """
        Get details of Bridged management interface
            - find the management network and get the name of the
              network
            - get all network_interface under the MS of type bridge
            - get the bridge with the name of the management network
            - record the name, host_device and ip address in a
              dictionary

        Args:

        Returns: -
            Dictionary with management network name, device_name of
            bridge, and Management IP address
        """
        mgmt_network_name = ''
        mgmt_network_device_name = ''
        mgmt_network_ip_addr = ''
        mgmt_network_ip_addr_ms = self.get_node_att(
            self.management_server,
            "ipv4")
        mgmt_network_name = self.get_management_network_name(
            self.management_server)
        self.assertTrue(mgmt_network_name)

        mgmt_network_bridge_urls = self.find(
            self.management_server,
            self.primary_node_url,
            "bridge")
        for bridge in mgmt_network_bridge_urls:
            if self.get_props_from_url(self.management_server,
                                       bridge,
                                       'network_name') == mgmt_network_name:
                mgmt_network_device_name = self.get_props_from_url(
                    self.management_server,
                    bridge,
                    'device_name')
                mgmt_network_ip_addr = self.get_props_from_url(
                    self.management_server,
                    bridge,
                    'ipaddress')
                break
        self.assertTrue(mgmt_network_device_name)
        self.assertTrue(mgmt_network_ip_addr)

        return {'network_name': mgmt_network_name,
                'host_device': mgmt_network_device_name,
                'ipaddress': mgmt_network_ip_addr,
                'ipaddress_ms': mgmt_network_ip_addr_ms}

    def get_bridge_info_for_dhcp_network(self):
        """
        Get details of Bridged dhcp interface
            - find the dhcp network and get the name of the network
            - get all network_interface under the MS of type bridge
            - get the bridge with the name of the dhcp network
            - record the name, host_device and ip address in a
              dictionary

        Args:

        Returns: -
            Dictionary with dhcp network name, device_name of bridge,
            and dhcp IP address
        """

        dhcp_network_name = ''
        dhcp_network_device_name = ''
        dhcp_network_ip_addr = ''
        dhcp_network_ip_addr_ms = self.get_node_att(
            self.management_server,
            "ipv4")
        dhcp_network_name = self.get_dhcp_network_name(
            self.management_server)
        self.assertTrue(dhcp_network_name)

        dhcp_network_bridge_urls = self.find(
            self.management_server,
            self.primary_node_url,
            "bridge")
        for bridge in dhcp_network_bridge_urls:
            if self.get_props_from_url(self.management_server,
                                       bridge,
                                       'network_name') == dhcp_network_name:
                dhcp_network_device_name = self.get_props_from_url(
                    self.management_server,
                    bridge,
                    'device_name')
                dhcp_network_ip_addr = self.get_props_from_url(
                    self.management_server,
                    bridge,
                    'ipaddress')
                break
        self.assertTrue(dhcp_network_device_name)
        self.assertTrue(dhcp_network_ip_addr)

        return {'network_name': dhcp_network_name,
                'host_device': dhcp_network_device_name,
                'ipaddress': dhcp_network_ip_addr,
                'ipaddress_ms': dhcp_network_ip_addr_ms}

    def get_dhcp_network_name(self, ms_node):
        """
        Description:
            Get dhcp network name.

        Args:
           ms_node (str) : The MS node with the deployment tree.

        Results:
            dhcp network name or None if not found.
        """
        # GET NETWORKS
        networks = self.find(ms_node, "/infrastructure", "network")

        for network_url in networks:
            props = self.get_props_from_url(ms_node, network_url)
            if 'dhcp' in props["name"]:
                return props["name"]

        return None

    @staticmethod
    def order_nodes(node_vnames, conf, service):
        """Sort LITP nodes paths for a particular service, accordingly
        to the order defined in conf['nodes_per_cs'] in
        generate_plan_conf_service(). conf['nodes_per_cs'] holds a list
         of numeric values representing nodes defined per
        vcs-clustered-service. With this hook, we can modify and
        utilize the nodes order as suits,
        ex.:
        conf['nodes_per_cs'] = {
            'CS24': [2, 1]
            }

        Args: node_vnames (list): Item names of LITP nodes

              conf (str): output of generate_plan_conf_service()

              service (str): name of a clustered service

        Returns:
          list. The list of LITP node paths, ordered according to
          conf['nodes_per_cs'].
        """

        return [node_vnames[node_num - 1]
                for node_num in conf['nodes_per_cs'][service]]

    def generate_execute_cs_cli(self, conf, vcs_cluster_url, cs_name):
        """
        This function will generate and execute the CLI to create the
        clustered services

        Args:
            conf (dict): configuration details for clustered-services

            vcs_cluster_url (str): Model url of vcs cluster item

            cs_name (str): clustered-service name

        Returns: -
        """

        dep_list = self.libvirt.define_online_ordering_dependencies()

        # Get the VCS related CLI commands
        cli_data = self.vcs.generate_cli_commands(vcs_cluster_url,
                                                  conf, cs_name,
                                                  "vm-service",
                                                  dep_list)

        #############################################################
        # This section of code will add the nodes to the CS
        #############################################################

        # Find cluster node urls
        node_urls = self.find(self.management_server,
                              vcs_cluster_url,
                              "node")

        # Order the node list according to how they are define in the config
        node_vnames = [url.split('/')[-1] for url in node_urls]
        node_vnames_ordered = self.order_nodes(node_vnames, conf, cs_name)

        # Create clustered-service in the model
        cs_options = cli_data['cs']['options'] + \
                     " node_list='{0}'".format(",".join(node_vnames_ordered))
        self.execute_cli_create_cmd(self.management_server,
                                    cli_data['cs']['url'],
                                    cli_data['cs']['class_type'],
                                    cs_options)

        # Create lsb apps in the model
        self.execute_cli_create_cmd(self.management_server,
                                    cli_data['apps']['url'],
                                    cli_data['apps']['class_type'],
                                    cli_data['apps']['options'])

        # Create all IPs associated with the lsb-app
        for ip_data in cli_data['ips']:
            self.execute_cli_create_cmd(self.management_server,
                                        ip_data['url'],
                                        ip_data['class_type'],
                                        ip_data['options'])

        # Create all packages associated with lsb-app
        for pkg_data in cli_data['pkgs']:
            self.execute_cli_create_cmd(self.management_server,
                                        pkg_data['url'],
                                        pkg_data['class_type'],
                                        pkg_data['options'])

        # Create the HA service config item
        if 'ha_service_config' in cli_data.keys():
            self.execute_cli_create_cmd(self.management_server,
                                cli_data['ha_service_config']['url'],
                                cli_data['ha_service_config']['class_type'],
                                cli_data['ha_service_config']['options'])

        # Create pkgs under the lsb-app
        for pkg_link_data in cli_data['pkg_links']:
            self.execute_cli_inherit_cmd(self.management_server,
                                         pkg_link_data['child_url'],
                                         pkg_link_data['parent_url'])

        self.execute_cli_inherit_cmd(self.management_server,
                                     cli_data['apps']['app_url_in_cluster'],
                                     cli_data['apps']['url'])

    def generate_execute_vm_cli(self, conf, vcs_cluster_url, cs_name,
                                ipaddresses):
        """
        This function will generate and execute the VM related CLI to
        create the VM related items

        Args:
            conf (dict): configuration details for clustered-services

            vcs_cluster_url (str): Model url of vcs cluster item

            cs_name (str): clustered-service name

            ipaddresses (dict): dynamically generated dictionary of ip
                addresses per network

        Returns: -
        """
        # Get the Libvirt related CLI commands
        replace_map = {'ms_host': self.ms_hostname,
                       'sfs_host': self.sfs_hostname,
                       'sfs_ip': self.sfs_ip}

        mgmt_bridge_info = self.get_bridge_info_for_mgmt_network()
        dhcp_bridge_info = self.get_bridge_info_for_dhcp_network()
        ms_host_name = self.get_management_node_filename()

        cli_data = self.libvirt.generate_cli_commands(
            conf,
            vcs_cluster_url,
            cs_name, ipaddresses,
            ms_host_name,
            mgmt_bridge_info,
            dhcp_bridge_info,
            self.sfs_hostname,
            self.sfs_ip,
            replace_map=replace_map)

        for host in cli_data['vm_hosts']:
            # Create VM hosts in the model
            self.execute_cli_create_cmd(self.management_server,
                                        host['url'],
                                        host['class_type'],
                                        host['options'])

        for interface in cli_data['vm_interfaces']:
            # Create VM interfaces in the model
            self.execute_cli_create_cmd(self.management_server,
                                        interface['url'],
                                        interface['class_type'],
                                        interface['options'])

        for interface in cli_data['vm_interfaces_ips']:
            # Update inherited VM interfaces in the model
            self.execute_cli_update_cmd(self.management_server,
                                        interface['url'],
                                        interface['options'])

        for repo in cli_data['vm_repos']:
            # Create VM repos in the model
            self.execute_cli_create_cmd(self.management_server,
                                        repo['url'],
                                        repo['class_type'],
                                        repo['options'])

        for mount in cli_data['vm_nfs_mounts']:
            # Create VM NFS Mounts in the model
            self.execute_cli_create_cmd(self.management_server,
                                        mount['url'],
                                        mount['class_type'],
                                        mount['options'])

        for key in cli_data['vm_ssh_keys']:
            # Create VM SSH Keys in the model
            self.execute_cli_create_cmd(self.management_server,
                                        key['url'],
                                        key['class_type'],
                                        key['options'])

    def generate_execute_vm_cli_vmimage(self, conf, vm_image):
        """
        This function will generate and execute the CLI for VM image

        Args:
            conf (dict): configuration details for clustered-services

            cs_name (str): clustered-service name

        Returns: -
        """
        replace_map = {
            'ms_host': self.ms_hostname,
        }

        cli_data = self.libvirt.generate_cli_commands_vmimage(conf, vm_image,
            replace_map=replace_map)

        # Create VM images in the model
        self.execute_cli_create_cmd(self.management_server,
                                    cli_data['vm_images']['url'],
                                    cli_data['vm_images']['class_type'],
                                    cli_data['vm_images']['options'])

    def generate_execute_create_sfs_mount(self, mount_indexes):
        """
        This function executes cli to create shares on the SFS

        Args:
            mount_indexes(list): list of integers for mount indexes,
            e.g [1, 2, 3]

        Returns: -
        """
        for index in mount_indexes:
            fs_path = '/vx/story7815-mount_{0}'.format(index)
            fs_url = self.pool_url + \
                     '/file_systems/fs{0}'.format(index)
            fs_type = 'sfs-filesystem'
            fs_options = {
                'size': '10M',
                'path': fs_path}
            options = ""
            for obj_prop, value in fs_options.items():
                options = options + obj_prop + "='" + value + "' "
            self.execute_cli_create_cmd(self.management_server,
                                        fs_url,
                                        fs_type,
                                        options)
            export_type = 'sfs-export'
            export_url = fs_url + '/exports/mount_{0}'.format(index)
            export_options = {
                'ipv4allowed_clients': '192.168.0.0/24',
                'options': 'rw,no_root_squash'}
            options = ""
            for obj_prop, value in export_options.items():
                options = options + obj_prop + "='" + value + "' "
            self.execute_cli_create_cmd(self.management_server,
                                        export_url,
                                        export_type,
                                        options)

    def configure_default_gateway(self, nic_urls, gateway, eth_type):
        """
        Finds the nic that matches the device_name to
        configure the default gateway for
        Args:
        nic_url(str): The service to be modified
        gateway(string): value of the gateway
        eth_type(str): Name of device to match
        """
        for nic in nic_urls:
            device_name = self.get_props_from_url(self.management_server,
                                                  nic,
                                                  filter_prop="device_name")
            if device_name == eth_type:
                self.set_default_gateway_ipaddress(nic, gateway)

    def set_default_gateway_ipaddress(self, srv_url, gateway):
        """
        Configures the default gateway property
        Args:
        srv_url(str): The service to be modified
        gateway(string): value of the gateway
        """
        if not self.get_props_from_url(self.management_server,
                                       srv_url,
                                       filter_prop="gateway"):
            self.execute_cli_update_cmd(self.management_server,
                                        srv_url,
                                        'gateway={0}'.format(gateway))

    def setup_sfs_mount_points(self):
        """
        This function calls the methods to setup the SFS

        Args: -

        Returns: -
        """
        self.generate_execute_create_sfs_mount(range(1, 6))

    def create_cs_vm2(self):
        """
        Description:
            This test will generate the CLI which will deploy
            clustered-services which will then be used to by other
            tests
        Actions:
            1. Executes CLI to create model
        Results:
            CLI executes succesfully.
        """
        # Generate configuration for the plan
        # This configuration will contain the configuration for all
        # clustered-services to be created but only some of them will be used
        traffic_networks = ["traffic1", "traffic2"]
        vm_image = "vm_image_2"
        cleanup_command = '/tmp/cleanup_vm.sh'
        cleanup_command_infinite_loop = \
            '#!/usr/bin/bash\n' + \
            'while :\n' + \
            'do\n' + \
            '    echo "Press [CTRL+C] to stop.."' + \
            '    sleep 1\n' + \
            'done'

        config = \
            dict(self.vcs.generate_plan_conf(traffic_networks).items() +
                 self.libvirt.generate_conf_plan2().items())

        # Setup the SFS shares
        self.setup_sfs_mount_points()

        self.generate_execute_vm_cli_vmimage(config, vm_image)

        net_ip_addresses = self.generate_ip_address(config)

        self.generate_execute_cs_cli(config, self.vcs_cluster_url,
                                     self.cs_name)
        self.generate_execute_vm_cli(config, self.vcs_cluster_url,
                                     self.cs_name, net_ip_addresses)

        #Just one nic here eth0, so set to default gatway.
        # Find default gateway of MS
        gateway = \
            self.get_props_from_url(self.management_server, \
                self.get_default_route_path(self.management_server),
                filter_prop="gateway")

        service = self.find(self.management_server, "/software/",
                            "vm-service")[0]
        service_name = self.get_props_from_url(self.management_server,
                                               service, 'service_name')
        nic_urls = self.find(self.management_server, service[0],
                             "vm-network-interface")
        self.configure_default_gateway(nic_urls, gateway, "eth0")
        self.create_file_on_node(self.get_managed_node_filenames()[1],
                                 cleanup_command,
                                 cleanup_command_infinite_loop.split('\n'),
                                 su_root=True, file_permissions='777')

        self.execute_cli_update_cmd(self.management_server, service, \
                                'cleanup_command={0}'.format(cleanup_command))

        return service, service_name

    @attr('all', 'revert')
    def test_01_p_stop_undefine_timeout_positive(self):
        """
        Description:
            To ensure that it is possible to run the litpmnlibvirt
            adaptor script command argument stop-undefine with an
            option --stop-timeout=N where N is the time in seconds
            (a positive integer, that is, > 0).
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory
                location on the node.
             3. Copy the json file containing the vm properties to the
                required directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop-undefine command
                with --stop-timeout=--33

        Results:
            The vm is deployed successfully and successfully cycles
            through the commands issued against it.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9693_0"
        this_app_data_dir = self.instances_data_dir + \
                            '/{0}/'.format(vm_service_name)
        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            installed_libvirt = \
                self.check_pkgs_installed(self.primary_node,
                                          ["libvirt-0.10.2-18.el6.x86_64"])

            if not installed_libvirt:
                self.install_rpm_on_node(self.primary_node, ['libvirt'])
                installed_libvirt = True

            self.start_service(self.primary_node, 'libvirtd')

            # STEP 1
            adaptor_installed = \
                self.check_pkgs_installed(
                    self.primary_node,
                    [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
            if not adaptor_installed:
                self.install_rpm_on_node(
                    self.primary_node,
                    [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
                adaptor_installed = True

            # STEP 2
            dir_contents = \
                self.list_dir_contents(self.primary_node, self.libvirt_dir)
            image_dir_name = self.images_dir.split('/')[-1]
            if image_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.images_dir,
                                        su_root=True)

            self.cp_file_on_node(
                self.primary_node,
                '/tmp/{0}'.format(self.temp_image_name),
                test_constants.LIBVIRT_IMAGE_DIR + \
                '/{0}'.format(self.temp_image_name),
                su_root=True)

            # CREATE THE INSTANCE DIRECTORY AND THE TEST APPLICATION
            # SUBDIRECTORY
            instances_dir_name = self.instances_data_dir.split('/')[-1]
            if instances_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.instances_data_dir,
                                        su_root=True)

            self.create_dir_on_node(self.primary_node,
                                    this_app_data_dir, su_root=True)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name, self.primary_node)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine --stop-timeout=33')
        finally:
            self.remove_item(
                self.primary_node,
                self.images_dir + '/{0}'.format(self.temp_image_name),
                su_root=True)
            vm_undefine_cmd = \
                self.libvirt.get_virsh_undefine_cmd(vm_service_name)
            self.run_command(self.primary_node, vm_undefine_cmd, su_root=True)
            if installed_libvirt:
                self.remove_rpm_on_node(self.primary_node, ["libvirt"])
            if adaptor_installed:
                self.remove_rpm_on_node(
                    self.primary_node,
                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

    @attr('all', 'revert')
    def test_04_p_stop_undefine_no_timeout(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt
            adaptor to stop a vm service app using stop-undefine
            without --stop-timeout option argument.
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory
                location on the node.
             3. Copy the json files containing the vm properties to the
                required directory location on the node.
             4. Issue the service <vm_name> start command for vm
                service.
             5. Issue the service <vm_name> status command for vm
                service.
             6. Issue the service <vm_name> stop-undefine command on
                vm service.

        Results:
            The vm's are deployed successfully and successfully cycles
            through the commands issued against them.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9693_1"
        this_app_data_dir = self.instances_data_dir + \
                            '/{0}/'.format(vm_service_name)

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            installed_libvirt = \
                self.check_pkgs_installed(self.primary_node,
                                          ["libvirt-0.10.2-18.el6.x86_64"])

            if not installed_libvirt:
                self.install_rpm_on_node(self.primary_node, ['libvirt'])
                installed_libvirt = True

            self.start_service(self.primary_node, 'libvirtd')

            # STEP 1
            adaptor_installed = \
                self.check_pkgs_installed(
                    self.primary_node,
                    [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
            if not adaptor_installed:
                self.install_rpm_on_node(
                    self.primary_node,
                    [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
                adaptor_installed = True

            # STEP 2
            dir_contents = \
                self.list_dir_contents(self.primary_node, self.libvirt_dir)
            image_dir_name = self.images_dir.split('/')[-1]
            if image_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.images_dir,
                                        su_root=True)

            self.cp_file_on_node(
                self.primary_node,
                '/tmp/{0}'.format(self.temp_image_name),
                test_constants.LIBVIRT_IMAGE_DIR + \
                '/{0}'.format(self.temp_image_name),
                su_root=True)

            # CREATE THE INSTANCE DIRECTORY AND THE TEST APPLICATION
            # SUBDIRECTORY
            instances_dir_name = self.instances_data_dir.split('/')[-1]
            if instances_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.instances_data_dir,
                                        su_root=True)

            self.create_dir_on_node(self.primary_node,
                                    this_app_data_dir, su_root=True)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name, self.primary_node)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine')
        finally:
            self.remove_item(
                self.primary_node,
                self.images_dir + '/{0}'.format(self.temp_image_name),
                su_root=True)
            vm_undefine_cmd = \
                self.libvirt.get_virsh_undefine_cmd(vm_service_name)
            self.run_command(self.primary_node, vm_undefine_cmd, su_root=True)
            if installed_libvirt:
                self.remove_rpm_on_node(self.primary_node, ["libvirt"])
            if adaptor_installed:
                self.remove_rpm_on_node(
                    self.primary_node,
                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

    @attr('all', 'revert')
    def test_05_n_stop_undefine_stop_timeout_elapses(self):
        """
        Description:
            Make "stop-undefine" command to hang. Check that after 33
            seconds, the VM is forcefully destroyed and the VM is
            undefined (the result should be similar with running :
            "/bin/systemctl force-stop-undefine test-vm-service-3").
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory
                location on the node.
             3. Copy the json file containing the vm properties to the
                required directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Connect to service <vm_name> and remove /sbin/shutdown
                to simulate a timeout failure for stop-undefine.
             7. Issue the service <vm_name> stop-undefine
                --stop-timeout=33 command.
             8. Check LIBVIRT LOGS to see if force-stop-undefine was
                called.
        Results:
            VM is forcefully destroyed and undefined if stop-undefine
            timesout.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9693_0"
        error_grep_returnc = 2
        this_app_data_dir = \
            self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # STEP 1
            installed_libvirt, adaptor_installed = \
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image_name,
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
                                     su_root=True)

            meta_data_content = self.prepare_metadata_content(bridge_urls,
                                                              check_ipaddress)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name,
                                                            meta_data_content)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')
            self.wait_for_vm_start(vm_service_name, self.primary_node)
            self.add_vm_to_nodelist(check_ipaddress, check_ipaddress,
                        username=test_constants.LIBVIRT_VM_USERNAME,
                        password=test_constants.LIBVIRT_VM_PASSWORD)
            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6 REMOVE  /sbin/shutdown command
            cmd = "/bin/rm -f /sbin/shutdown"
            _, stderr, return_code = \
            self.run_command_via_node(self.primary_node, check_ipaddress, cmd,
                                username=test_constants.LIBVIRT_VM_USERNAME,
                                password=test_constants.LIBVIRT_VM_PASSWORD)
            self.assertEqual(0, return_code)
            self.assertEqual([], stderr)

            # STEP 7
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine --stop-timeout=33')

            # STEP 8 CHECK force-stop-undefine was called
            grep_cmd = \
                self.rhc.get_grep_file_cmd(test_constants.LITP_LIBVIRT_LOG,
                                           "calling force-stop")

            stdout, stderr, returnc = self.run_command(self.primary_node,
                                                       grep_cmd)

            self.assertNotEqual(error_grep_returnc, returnc)
            self.assertEqual([], stderr)
            self.assertNotEqual([], stdout)
        finally:
            self.cleanup_after_test(vm_service_name,
                                    installed_libvirt,
                                    adaptor_installed)

    @attr('all', 'revert')
    def test_06_n_cleanup_command_without_stop_undefine(self):
        """
        Description: Create a VCS Clustered Service having
            cleanup_command set to a custom cleanup script.
            If the custom cleanup script hangs check litpmnlibvirt is
            not calling VM destroy and is not undefining the vm service
            If the custom cleanup command hangs then an administrator
            has to intervene to break the continuous clean
            loop to make the cleanup procedure to complete.
        Actions:
            1. Create a VCS Clustered Service.
            2. Update cleanup_command to use a custom generated cleanup
               script like 'cleanup_vm'.sh. cleanup_vm.sh script will
               run an infinite loop.
            3. Create/Run PLAN.
            4. After Plan finished successfully having the VCS
               Clustered Service created, run "/usr/bin/systemctl stop
               test-vm-service-2"
            5. Cleanup Procedure will start calling the custom cleanup
               script 'cleanup_vm.sh'.
            6. Cleanup Procedure will timeout as the custom script will
               run an infinite loop.
            7. Check LIBVIRT is not calling vm destroy and is not
               undefining the vm service.
            8. Update VCS Clustered Service clean command directly on
               the node via VCS commands to:
               '/usr/share/litp_libvirt/vm_utils test-vm-service-2
               stop'
            9. Update clean command via model, create and run plan
            10. Start back the test-vm-service.
        Results:
            LIBVIRT should not call VM Destroy and should not undefine
            a vm-service when the cleanup procedure using a custom
            generated cleanup script is timing out.
        """
        plan_timeout_mins = 60
        secondary_node = self.get_managed_node_filenames()[1]

        # CREATE A LIBVIRT VCS CLUSTERED SERVICE HAVING cleanup command using
        # A CUSTOM GENERATED CLEANUP SCRIPT /tmp/cleanup_vm.sh
        # THE LIBVIRT VCS CLUSTERED SERVICE IS CONTAINING test-vm-service-1
        # AS SOFTWARE APPLICATION
        vm_service, vm_service_name = self.create_cs_vm2()

        # CREATE AND EXECUTE PLAN AND EXPECT IT TO SUCCEED
        self.execute_cli_createplan_cmd(self.management_server)
        self.execute_cli_runplan_cmd(self.management_server)
        self.assertTrue(self.wait_for_plan_state(
            self.management_server,
            test_constants.PLAN_COMPLETE,
            plan_timeout_mins
        ))

        # RUN STOP COMMAND AGAINST test-vm-service-1. EXPECTING VCS TO CALL
        # CLEANUP COMMAND AS THE RESOURCE BECOME OFFLINE ON ITS OWN
        stop_cmd = self.rhc.get_systemctl_stop_cmd(vm_service_name)
        stop_out = self.run_command(secondary_node, stop_cmd, su_root=True,
                                    default_asserts=True)
        self.assertEqual([], stop_out[0], "stop cmd was not successful")

        # CUSTOM CLEANUP SCRIPT IS RUNNING AN INFINITE LOOP.
        # CHECK CLEANUP COMMAND TIMESOUT
        self.wait_for_log_msg(secondary_node,
                              'resource became OFFLINE unexpectedly,' + \
                              ' on its own.',
                              test_constants.VCS_ENG_A_LOG_FILE, 600)

        self.wait_for_log_msg(secondary_node,
                              'clean procedure did not complete within ' + \
                              'the expected time.',
                              test_constants.VCS_ENG_A_LOG_FILE, 600)

        # CHECK VCS IS NOT CALLING DESTROY SERVICE
        grep_cmd = \
            self.rhc.get_grep_file_cmd(test_constants.LITP_LIBVIRT_LOG,
                                       'Attempting to destroy Service',
                                       file_access_cmd='tail -n 3')
        stdout, stderr, returnc = self.run_command(secondary_node, grep_cmd)
        self.assertEqual(1, returnc)
        self.assertEqual([], stderr)
        self.assertEqual([], stdout)

        self.log("info", "Update VCS Clustered Service clean command "
                         "directly on the node via VCS commands")
        # Behaviour of the functionality that deals with failed VCS clean
        # action has changed with RHEL7 and now administrator intervention
        # is required. See the following ticket:
        # https://jira-oss.seli.wh.rnd.internal.ericsson.com/browse/TORF-487749
        cluster_id = self.vcs_cluster_url.split('/')[-1]
        sg_name = self.vcs.generate_clustered_service_name(self.cs_name,
                                                           cluster_id)
        get_resource_cmd = self.vcs.get_hagrp_resource_list_cmd(sg_name)
        resource_name, _, _ = self.run_command(secondary_node,
                                               get_resource_cmd,
                                               su_root=True,
                                               default_asserts=True)
        self.assertNotEqual([], resource_name)

        cleanup_cmd = "/usr/share/litp_libvirt/vm_utils {0} stop". \
            format(vm_service_name)
        enable_vcs_conf = self.vcs.get_haconf_cmd('-makerw')
        modify_clean_cmd = self.vcs.get_hares_cmd('-modify {0} CleanProgram '
                                '"{1}"'.format(resource_name[0], cleanup_cmd))
        disable_vcs_conf = self.vcs.get_haconf_cmd("-dump -makero")
        for cmd in [enable_vcs_conf, modify_clean_cmd, disable_vcs_conf]:
            self.run_command(secondary_node, cmd, su_root=True,
                             default_asserts=True)

        # UPDATE CLEANUP COMMAND TO USE LIBVIRT STOP COMMAND.
        self.execute_cli_update_cmd(self.management_server, vm_service,
                                    'cleanup_command="{0}"'.format(cleanup_cmd)
                                    )

        # CREATE AND EXECUTE PLAN AND EXPECT IT TO SUCCEED
        self.execute_cli_createplan_cmd(self.management_server)
        self.execute_cli_runplan_cmd(self.management_server)
        self.assertTrue(self.wait_for_plan_state(
            self.management_server,
            test_constants.PLAN_COMPLETE,
            plan_timeout_mins
        ))

        # START VM SERVICE.
        start_cmd = self.rhc.get_systemctl_start_cmd(vm_service_name)
        start_out = self.run_command(secondary_node, start_cmd, su_root=True,
                                     default_asserts=True)
        self.assertEqual([], start_out[0], "start cmd was not successful")

        # WAIT FOR VM TO START
        self.wait_for_vm_start(vm_service_name, secondary_node, 'tmo-vm-2')
