"""
COPYRIGHT Ericsson 2019
The copyright to the computer program(s) herein is the property of
Ericsson Inc. The programs may be used and/or copied only with written
permission from Ericsson Inc. or in accordance with the terms and
conditions stipulated in the agreement/contract under which the
program(s) have been supplied.

@since:     Nov 2014
@author:    Philip Daly
@summary:   As a LITP Developer I want a libvirt adaptor so that I can manage
            a virtual machine on a peer node.
            Agile: LITPCDS-6209
"""

from litp_generic_test import GenericTest, attr
from redhat_cmd_utils import RHCmdUtils
from libvirt_utils import LibvirtUtils
import test_constants


class Story6209(GenericTest):
    """
    LITPCDS-6209:
    As a LITP Developer I want a libvirt adaptor so that I can manage a virtual
    machine on a peer node.
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
        super(Story6209, self).setUp()
        self.rh_os = RHCmdUtils()
        self.libvirt = LibvirtUtils()
        self.temp_image_name = "rhel.img"
        self.adaptor_pkg_name = test_constants.LIBVIRT_ADAPTOR_PKG_NAME
        self.libvirt_dir = test_constants.LIBVIRT_DIR
        self.temp_image_location = test_constants.VM_IMAGE_MS_DIR
        self.instances_data_dir = test_constants.LIBVIRT_INSTANCES_DIR
        self.images_dir = test_constants.LIBVIRT_IMAGE_DIR
        self.management_server = self.get_management_node_filename()
        self.list_managed_nodes = self.get_managed_node_filenames()
        self.primary_node = self.list_managed_nodes[0]
        # CHECK WHETHER THE IMG IS IN THE TMP DIR ON THE NODE - IF NOT COPY
        dir_contents = \
        self.list_dir_contents(self.primary_node,
                               '/tmp')
        if self.temp_image_name not in dir_contents:
            ms_dir_contents = \
            self.list_dir_contents(self.management_server,
                                   self.temp_image_location)

            self.wget_image_to_node(self.management_server, self.primary_node,
                                    ms_dir_contents[0], '/tmp',
                                    self.temp_image_name)

    def tearDown(self):
        """
        Description:
            Runs after every single test
        Actions:
            -
        Results:
            The super class prints out diagnostics and variables
        """
        super(Story6209, self).tearDown()

    def wait_for_vm_start(self, vm_service_name):
        """
        wait for virtual machine to completely start.
        Check by connecting to the virtual machine using virsh console.
        """
        expected_stdout = 'localhost.localdomain.localdomain login:'
        self.wait_for_cmd(self.primary_node,
                          "virsh console {0}".format(vm_service_name),
                          -1,
                          expected_stdout=expected_stdout,
                          su_root=True)

    @attr('all', 'revert')
    def test_01_p_deploy_1_vm(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            deploy a virtual machine on the node on which the adaptor is
            installed.

            This test also includes the automation of
            test_05_n_multiple_start
            test_06_n_multiple_stop

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
            The vm is deployed successfully and successfully cycles through
            the commands issued against it.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp6209_0"
        this_app_data_dir = \
        self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            installed_cmd = \
            self.rh_os.check_pkg_installed(["libvirt-0.10.2-18.el6.x86_64"])
            _, _, return_code = \
            self.run_command(self.primary_node, installed_cmd, su_root=True)
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

            # STEP 1
            installed_cmd = \
            self.rh_os.check_pkg_installed([self.adaptor_pkg_name])
            _, _, return_code = \
            self.run_command(self.primary_node, installed_cmd, su_root=True)
            if return_code != 0:
                adaptor_installed = True
                self.install_rpm_on_node(
                    self.primary_node,
                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

            # STEP 2
            dir_contents = \
            self.list_dir_contents(self.primary_node, self.libvirt_dir)
            image_dir_name = self.images_dir.split('/')[-1]
            if image_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.images_dir,
                                        su_root=True)

            self.cp_file_on_node(self.primary_node,
                                 '/tmp/{0}'.format(self.temp_image_name),
                                 test_constants.LIBVIRT_IMAGE_DIR +
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
                                    this_app_data_dir,
                                    su_root=True)
            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node, this_app_data_dir +
                                     '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True,
                                     add_to_cleanup=False)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name)

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

            # EXECUTING TESTS 05 AND 06
            # TEST 05
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name)

            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            # TEST 06
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop')
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop')

        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image_name),
                             su_root=True)
            vm_undefine_cmd = \
            self.libvirt.get_virsh_undefine_cmd(vm_service_name)
            self.run_command(self.primary_node, vm_undefine_cmd, su_root=True)

            if installed_libvirt:
                cmd = self.rhc.get_yum_remove_cmd(["libvirt"])
                self.run_command(self.primary_node, cmd, su_root=True)
            if adaptor_installed:
                self.remove_rpm_on_node(
                    self.primary_node,
                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

    @attr('all', 'revert')
    def test_02_p_deploy_3_vm(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            deploy a series of virtual machines on the node on which the
            adaptor is installed.

        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json files containing the vm properties to the
                required directory location on the node.
             4. Issue the service <vm_name> start command for each service.
             5. Issue the service <vm_name> status command for each service.
             6. Issue the service <vm_name> stop command for each service.

        Results:
            The vm's are deployed successfully and successfully cycles through
            the commands issued against them.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_names = ["testapp6209_1", "testapp6209_2", "testapp6209_3"]

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            installed_cmd = \
            self.rh_os.check_pkg_installed(["libvirt-0.10.2-18.el6.x86_64"])
            _, _, return_code = \
            self.run_command(self.primary_node, installed_cmd, su_root=True)
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
            self.run_command(self.primary_node, start_libvirt_cmd,
                             su_root=True)
            self.assertEqual(0, return_code)

            # STEP 1
            installed_cmd = \
            self.rh_os.check_pkg_installed([self.adaptor_pkg_name])
            _, _, return_code = \
            self.run_command(self.primary_node, installed_cmd, su_root=True)
            if return_code != 0:
                adaptor_installed = True
                self.install_rpm_on_node(
                    self.primary_node,
                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)

            # STEP 2
            dir_contents = \
            self.list_dir_contents(self.primary_node, self.libvirt_dir)
            image_dir_name = self.images_dir.split('/')[-1]
            if image_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.images_dir,
                                        su_root=True)

            self.cp_file_on_node(self.primary_node,
                                 '/tmp/{0}'.format(self.temp_image_name),
                                 test_constants.LIBVIRT_IMAGE_DIR +
                                 '/{0}'.format(self.temp_image_name),
                                 su_root=True)

            # CREATE THE INSTANCE DIRECTORY AND THE TEST APPLICATION
            # SUBDIRECTORY
            instances_dir_name = self.instances_data_dir.split('/')[-1]
            if instances_dir_name not in dir_contents:
                self.create_dir_on_node(self.primary_node,
                                        self.instances_data_dir,
                                        su_root=True)
            for vm_name in vm_service_names:
                this_app_data_dir = \
                self.instances_data_dir + '/{0}/'.format(vm_name)
                self.create_dir_on_node(self.primary_node,
                                        this_app_data_dir,
                                        su_root=True)
                # STEP 3
                config_file_dump = self.libvirt.compile_vm_config_file()
                self.create_file_on_node(self.primary_node, this_app_data_dir +
                                         '/config.json',
                                         config_file_dump.split('\n'),
                                         su_root=True,
                                         add_to_cleanup=False)

                self.create_instance_data_files_in_instance_dir(
                    self.primary_node,
                    vm_name)

                # STEP 4
                self.run_libvirt_service_cmd(self.primary_node,
                                             vm_name, 'start')
                self.wait_for_vm_start(vm_name)

                # STEP 5
                self.run_libvirt_service_cmd(
                    self.primary_node, vm_name,
                    'status')

                # STEP 6
                self.run_libvirt_service_cmd(
                    self.primary_node, vm_name,
                    'stop')
        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image_name),
                             su_root=True)
            for vm_name in vm_service_names:
                vm_undefine_cmd = \
                self.libvirt.get_virsh_undefine_cmd(vm_name)
                self.run_command(self.primary_node, vm_undefine_cmd,
                                 su_root=True)

            if installed_libvirt:
                cmd = self.rhc.get_yum_remove_cmd(["libvirt"])
                self.run_command(self.primary_node, cmd, su_root=True)
            if adaptor_installed:
                self.remove_rpm_on_node(
                    self.primary_node,
                    test_constants.LIBVIRT_ADAPTOR_PKG_NAME)
            # REMOVE THE IMAGE FROM THE NODE
            self.remove_item(self.primary_node,
                             '/tmp/{0}'.format(self.temp_image_name),
                             su_root=True)
