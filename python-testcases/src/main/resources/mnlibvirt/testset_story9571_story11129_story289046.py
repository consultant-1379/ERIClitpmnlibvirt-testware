"""
COPYRIGHT Ericsson 2019
The copyright to the computer program(s) herein is the property of
Ericsson Inc. The programs may be used and/or copied only with written
permission from Ericsson Inc. or in accordance with the terms and
conditions stipulated in the agreement/contract under which the
program(s) have been supplied.

@since:     July 2015
@author:    Stefan Ulian
@summary:   As a LITP User I want a means of undefining a VM so I have a
            comprehsive means of cleaning up a faulted VM.
            Agile: LITPCDS-9571
"""

from litp_generic_test import GenericTest, attr
from redhat_cmd_utils import RHCmdUtils
from libvirt_utils import LibvirtUtils
import test_constants


class Story9571(GenericTest):
    """
    LITPCDS-9571:
    As a LITP User I want a means of undefining a VM so I have a
    comprehensive means of cleaning up a faulted VM.
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
        super(Story9571, self).setUp()
        self.rh_os = RHCmdUtils()
        self.libvirt = LibvirtUtils()
        self.temp_image = "rhel.img"
        self.temp_image_1 = "rhel_1.img"
        self.rhel7_4_image = "rhel7_4.img"
        self.adaptor_pkg_name = test_constants.LIBVIRT_ADAPTOR_PKG_NAME
        self.libvirt_dir = test_constants.LIBVIRT_DIR
        self.temp_image_location = test_constants.VM_IMAGE_MS_DIR
        self.instances_data_dir = test_constants.LIBVIRT_INSTANCES_DIR
        self.images_dir = test_constants.LIBVIRT_IMAGE_DIR
        self.management_server = self.get_management_node_filename()
        self.list_managed_nodes = self.get_managed_node_filenames()
        self.primary_node = self.list_managed_nodes[0]
        self.libvirt_config_dir = test_constants.LIBVIRT_CONFIG_DIR
        self.cpu_tag_xml = "<cpu mode='host-passthrough'>"

        # CHECK WHETHER THE IMG IS IN THE TMP DIR ON THE NODE - IF NOT COPY
        dir_contents = \
            self.list_dir_contents(self.primary_node,
                                   '/tmp')
        if self.temp_image not in dir_contents:
            ms_dir_contents = \
                self.list_dir_contents(self.management_server,
                                       self.temp_image_location)

            self.wget_image_to_node(self.management_server, self.primary_node,
                                    ms_dir_contents[0], '/tmp',
                                    self.temp_image)
        # TORF-271798: RHEL7.4 image
        if self.rhel7_4_image not in dir_contents:
            self.wget_image_to_node(self.management_server, self.primary_node,
                                    "vm_test_image-5-1.0.7.qcow2", '/tmp',
                                    self.rhel7_4_image)

    def tearDown(self):
        """
        Description:
            Runs after every single test
        Actions:
            -
        Results:
            The super class prints out diagnostics and variables
        """
        super(Story9571, self).tearDown()

    def chk_dependencies_installed(self):
        """
        check whether libvirt is installed - if not then
        install libvirt on the node and start the service.
        """
        installed_libvirt = \
            self.check_pkgs_installed(self.primary_node,
                                      ["libvirt-0.10.2-18.el6.x86_64"])
        if not installed_libvirt:
            self.install_rpm_on_node(self.primary_node, ['libvirt'])
            installed_libvirt = True
        self.start_service(self.primary_node, 'libvirtd')
        adaptor_installed = \
            self.check_pkgs_installed(
                self.primary_node,
                [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
        if not adaptor_installed:
            self.install_rpm_on_node(
                self.primary_node,
                [test_constants.LIBVIRT_ADAPTOR_PKG_NAME])
            adaptor_installed = True

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

    def check_vm_dir_cont(self, this_app_data_dir):
        """
        Check contents of vm service directory
        Return .live files and vm images
        """
        # List to contain files to be copied after stop-undefine
        filesfound = []

        dirlist_before = self.list_dir_contents(self.primary_node,
                                                this_app_data_dir,
                                                su_root=True)
        # Get image name from config.json
        config_json = self.get_file_contents(self.primary_node,
                                             this_app_data_dir +
                                             'config.json',
                                             su_root=True)

        config_json_dict = eval(config_json[0])
        config_image = config_json_dict["vm_data"]["image"]

        for livefile in dirlist_before:
            if livefile.endswith('.live'):
                filesfound.append(livefile)
        filesfound.append(config_image)
        return filesfound

    def compare_vm_dir_cont(self, filesfound, this_app_data_dir):
        """
        Check contents of dir /last_undefined_vm of the vm service
        Check if correct files are stored in /last_undefined_vm
        after vm service is stopped
        """
        # List to contain files to be copied after stop-undefine
        newfiles = []

        # List of files that were copied after stop-undefine
        dirlist_after = self.list_dir_contents(self.primary_node,
                                               this_app_data_dir +
                                               'last_undefined_vm',
                                               su_root=True)
        self.assertTrue(dirlist_after, "Directory  not found")

        # Add timestamp to files found to compare to files after stop
        for foundfile in filesfound:
            newfiles.append(foundfile + '-' +
                            dirlist_after[0].split("-")[-1])
        # Put files in correct order
        newfiles[-2], newfiles[-1] = newfiles[-1], newfiles[-2]
        self.assertEqual(dirlist_after, newfiles,
                         'Correct files not copied')

    def confirm_files_in_vm_dir_cont(self, vm_files, dir_content):
        """
        Assert that all files in a given list are present in vm dir content
        provided
        Args:
            vm_files: (lst) A list of vm files to check
            dir_content: (lst) Content of the vm service dir
        """
        for vm_file in vm_files:
            self.assertTrue(
                self.is_text_in_list(vm_file, dir_content),
                '{0} file is not found in {1}'.format(vm_file,
                                                      dir_content))

    @attr('all', 'revert', 'story9571', 'story9571_tc01', 'torf271798_tc04',
          'torf271798_tc17', 'torf289046', 'torf289046_tc05',
          'torf289046_tc06', 'torf289046_tc09', 'cdb_priority1')
    def test_01_p_vm_stop_undefine_when_vm_started(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            successfully run stop-undefine command on a virtual machine that
            is in running state.
            Story11129
            When a stop-undefine or force-stop-undefine command is called with
            the litpvirt adaptor script then I should see the VM image along
            with live configuration files stored in a subdirectory
            TORF-289046: To better utilise the underlying CPU resources
            the following property shall be set for VM's deployed on
            hardware: <cpu mode='host-passthrough'>
            (./last_undefined_vm) of the instance directory
            TORF-271798: network-config v1 file should remain in the instance
            directory when un-defining a vm service

        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop-undefine command.
             7. Remove dir ./last_undefined_vm
             8. Issue the service <vm_name> start command.
             9. Issue the service <vm_name> status command.
             10. Issue the service <vm_name> stop-undefine command.
             11. Check the dir ./last_undefined_vm is recreated
             12. Load a different qcow2 image
             13. Start service
             14. Stop service with stop-undefine command
             15. Check qcow2 image overrides the image originally
                 stored in ./last_undefined_vm
             16. Check the vm configuration and ensure the following line
                 exists <cpu mode='host-passthrough'> in each vm.xml
                 on hardware env and not exist in virtual env.



        Results:
            The vm is deployed successfully and successfully cycles through
            the commands issued against it.
            Check is included for the story 11129 to check if the functionality
            to move vm-image and .live files to the new directory
             ./last_undefined_vm works correctly
            Checks thats when the dir /last_undefined_vm is removed
            it will get recreated when vm service is started and stopped again
            Check qcow2 image overrides the image originally stored in
            ./last_undefined_vm
            Checks that network-config v1 and meta-data files remain in the
            instance directory when un-defining a vm
            The following line exists <cpu mode='host-passthrough'>
            in each vm.xml on hardware env and doesn't exist in virtual env.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9571_0"
        this_app_data_dir = \
            self.instances_data_dir + '/{0}/'.format(vm_service_name)

        vm_data = {"vm_data": {"cpu": "2",
                               "ram": "256M",
                               "interfaces": {},
                               "hd": [],
                               "image": "rhel_1.img"}}

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            # STEP 1
            installed_libvirt, adaptor_installed = \
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image, this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True, add_to_cleanup=False)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')
            self.wait_for_vm_start(vm_service_name)
            filesfound = self.check_vm_dir_cont(this_app_data_dir)

            # TORF-271798 TC_04: un-define a rhel6 based vm service
            config_files = ['meta-data', 'network-config']
            self.confirm_files_in_vm_dir_cont(config_files, filesfound)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine --stop-timeout 20')

            self.compare_vm_dir_cont(filesfound, this_app_data_dir)

            # STEP 7
            # Remove dir last_undefined_vm
            cmd = "rm -rf {0}".format(this_app_data_dir + 'last_undefined_vm')
            self.run_command(self.primary_node, cmd, su_root=True)

            # STEP 8
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name)
            filesfound = self.check_vm_dir_cont(this_app_data_dir)
            self.confirm_files_in_vm_dir_cont(config_files, filesfound)

            # STEP 9
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 10
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine --stop-timeout 20')
            # Step 11
            self.compare_vm_dir_cont(filesfound, this_app_data_dir)
            # Step 12
            ms_dir_contents = \
                self.list_dir_contents(self.management_server,
                                       self.temp_image_location)

            self.wget_image_to_node(self.management_server, self.primary_node,
                                    ms_dir_contents[2], '/tmp',
                                    self.temp_image_1)

            self.cp_file_on_node(self.primary_node,
                                 '/tmp/{0}'.format(self.temp_image_1),
                                 test_constants.LIBVIRT_IMAGE_DIR +
                                 '/{0}'.format(self.temp_image_1),
                                 su_root=True)
            # Remove old config.json, to be replaced with new config.json
            # containing new image
            self.remove_item(self.primary_node, this_app_data_dir +
                             'config.json', su_root=True)

            config_file_dump = \
                self.libvirt.compile_vm_config_file(user_vm_data=vm_data)

            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True, add_to_cleanup=False)
            # STEP 13
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 14
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine --stop-timeout 20')
            # STEP 15
            dir_contents = \
                self.list_dir_contents(self.primary_node,
                                       this_app_data_dir + 'last_undefined_vm',
                                       su_root=True)
            # Check dir /last_undefined_vm contains new image
            self.assertTrue(self.is_text_in_list(self.temp_image_1,
                                                 dir_contents),
                            "Updated image not present")

            # TORF-271798 TC_17: un-define a RHEL7.4 based vm service
            self.cp_file_on_node(self.primary_node,
                                 '/tmp/{0}'.format(self.rhel7_4_image),
                                 '{0}/{1}'.format(
                                     test_constants.LIBVIRT_IMAGE_DIR,
                                     self.rhel7_4_image),
                                 su_root=True)

            # modify config.json file to contain rhel7.4 image
            config_json_path = '{0}/config.json'.format(this_app_data_dir)
            cmd = \
                self.rh_os.get_replace_str_in_file_cmd(self.temp_image_1,
                                                       self.rhel7_4_image,
                                                       config_json_path, '-i')
            self.run_command(self.primary_node, cmd, su_root=True,
                             add_to_cleanup=False, default_asserts=True)

            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.log("info", "Step 16: checking vm configuration has"
                             " <cpu mode='host-passthrough'>"
                             " in case of physical environment")
            path_to_xml = "{0}/testapp9571_0.xml".format(
                self.libvirt_config_dir)
            xmlfile = self.get_file_contents(self.primary_node,
                                             path_to_xml,
                                             tail=None, su_root=True,
                                             assert_not_empty=False)

            virt_what_cmd = test_constants.VIRT_WHAT_CMD
            virt_what_output = self.run_command(self.primary_node,
                                                virt_what_cmd,
                                                su_root=True)[0]
            is_bare_metal = (len(virt_what_output) == 0)
            if is_bare_metal:
                virsh_dumpxml_cmd = self.libvirt.get_virsh_dumpxml_cmd(
                    vm_service_name)
                virsh_dmpxml_stdout = self.run_command(self.primary_node,
                                                       virsh_dumpxml_cmd,
                                                       su_root=True)[0]
                self.assertTrue(self.is_text_in_list(
                    self.cpu_tag_xml,
                    virsh_dmpxml_stdout),
                    "The line <cpu mode='host-passthrough'> "
                    "doesn't exist in VM XML dump on a "
                    "hardware environment, XML dump: {0}".format(
                        str(virsh_dmpxml_stdout)))
                self.assertTrue(self.is_text_in_list(
                    self.cpu_tag_xml,
                    xmlfile),
                    "The line <cpu mode='host-passthrough'> "
                    "doesn't exist in VM XML file on a "
                    "hardware environment, XML file contents: {0}".format(
                        str(xmlfile)))

            else:
                self.assertFalse(self.is_text_in_list(
                    self.cpu_tag_xml,
                    xmlfile),
                    "The line <cpu mode='host-passthrough'> "
                    "doesn't exist in VM XML file on a "
                    "virtual environment, XML file contents: {0}".format(
                        str(xmlfile)))

            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')
            filesfound = self.check_vm_dir_cont(this_app_data_dir)
            self.confirm_files_in_vm_dir_cont(config_files, filesfound)

            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine --stop-timeout 20')

            self.compare_vm_dir_cont(filesfound, this_app_data_dir)

        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image),
                             su_root=True)
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.rhel7_4_image),
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

    @attr('all', 'revert', 'story9571', 'story9571_tc02', 'torf271798_tc04',
          'torf271798_tc17')
    def test_02_p_vm_force_stop_undefine_when_vm_started(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            successfully run force-stop-undefine on a virtual machine that is
            in running state.
            TORF-271798: network-config v1 file should remain in the instance
            directory when un-defining a vm service
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> force-stop-undefine command.

        Results:
            The vm is deployed successfully and successfully cycles through
            the commands issued against it.
            Check is included for the story 11129 to check if the functionality
            to move vm-image and .live files to the new directory
             ./last_undefined_vm works correctly
             Checks that network-config v1 and meta-data files remain in the
             instance directory when undefining a vm
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9571_0"
        this_app_data_dir = '{0}/{1}/'.format(self.instances_data_dir,
                                              vm_service_name)

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            # STEP 1
            installed_libvirt, adaptor_installed = \
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image, this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True, add_to_cleanup=False)

            self.create_instance_data_files_in_instance_dir(self.primary_node,
                                                            vm_service_name)

            # STEP 4
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')

            self.wait_for_vm_start(vm_service_name)
            filesfound = self.check_vm_dir_cont(this_app_data_dir)
            config_files = ['meta-data', 'network-config']
            self.confirm_files_in_vm_dir_cont(config_files, filesfound)

            # STEP 5
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            # STEP 6
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'force-stop-undefine')
            # run twice to make sure dir last_undefined_vm
            #  is not overwritten
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'force-stop-undefine')

            self.compare_vm_dir_cont(filesfound, this_app_data_dir)

            # TORF-271798 TC_17: un-define a RHEL7.4 based vm service
            self.cp_file_on_node(self.primary_node,
                                 '/tmp/{0}'.format(self.rhel7_4_image),
                                 '{0}/{1}'.format(
                                     test_constants.LIBVIRT_IMAGE_DIR,
                                     self.rhel7_4_image),
                                 su_root=True)

            # modify config.json file to contain rhel7.4 image
            config_json_path = '{0}config.json'.format(this_app_data_dir)
            cmd = \
                self.rh_os.get_replace_str_in_file_cmd(self.temp_image,
                                                       self.rhel7_4_image,
                                                       config_json_path, '-i')
            self.run_command(self.primary_node, cmd, su_root=True,
                             add_to_cleanup=False, default_asserts=True)

            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'start')
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'status')

            filesfound = self.check_vm_dir_cont(this_app_data_dir)
            self.confirm_files_in_vm_dir_cont(config_files, filesfound)
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'force-stop-undefine')
            self.compare_vm_dir_cont(filesfound, this_app_data_dir)

        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image),
                             su_root=True)
            self.remove_item(self.primary_node,
                             '{0}/{1}'.format(self.images_dir,
                                              self.rhel7_4_image),
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

    @attr('all', 'revert', 'story9571', 'story9571_tc03')
    def test_03_p_vm_stop_undefine_when_vm_stopped(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            successfully run stop-undefine on a virtual machine that was
            previously stopped
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop command.
             7. Issue the service <vm_name> stop-undefine command.
        Results:
            The vm is deployed successfully and successfully cycles through
            the commands issued against it.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9571_0"
        this_app_data_dir = \
            self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            # STEP 1
            installed_libvirt, adaptor_installed = \
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image, this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True, add_to_cleanup=False)

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

            # STEP 7
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'stop-undefine')

        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image),
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

    @attr('all', 'revert', 'story9571', 'story9571_tc04')
    def test_04_p_vm_force_stop_undefine_when_vm_stopped(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            deploy a virtual machine on the node on which the adaptor is
            installed.
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop command.
             7. Issue the service <vm_name> force-stop-undefine command.

        Results:
            The vm is deployed successfully and successfully cycles through
            the commands issued against it.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9571_0"
        this_app_data_dir = \
            self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            # STEP 1
            installed_libvirt, adaptor_installed = \
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image, this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True, add_to_cleanup=False)

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

            # STEP 7
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'force-stop-undefine')

        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image),
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

    @attr('all', 'revert', 'story9571', 'story9571_tc05')
    def test_05_p_vm_force_stop_undefine_after_vm_stopped_undefine(self):
        """
        Description:
            To ensure that it is possible to utilise the libvirt adaptor to
            deploy a virtual machine on the node on which the adaptor is
            installed.
        Actions:
             1. On node 1 install the libvirt adaptor via yum.
             2. Copy the vm template image to the required directory location
                on the node.
             3. Copy the json file containing the vm properties to the required
                directory location on the node.
             4. Issue the service <vm_name> start command.
             5. Issue the service <vm_name> status command.
             6. Issue the service <vm_name> stop-undefine command.
             7. Issue the service <vm_name> force-stop-undefine command.

        Results:
            The vm is deployed successfully and successfully cycles through
            the commands issued against it.
        """
        installed_libvirt = False
        adaptor_installed = False
        vm_service_name = "testapp9571_0"
        this_app_data_dir = \
            self.instances_data_dir + '/{0}/'.format(vm_service_name)

        try:
            # CHECK WHETHER LIBVIRT IS INSTALLED - IF NOT THEN
            # INSTALL LIBVIRT ON THE NODE AND START THE SERVICE
            # STEP 1
            installed_libvirt, adaptor_installed = \
                self.chk_dependencies_installed()

            # STEP 2
            self.copy_image_to_node(self.temp_image, this_app_data_dir)

            # STEP 3
            config_file_dump = self.libvirt.compile_vm_config_file()
            self.create_file_on_node(self.primary_node,
                                     this_app_data_dir + '/config.json',
                                     config_file_dump.split('\n'),
                                     su_root=True, add_to_cleanup=False)

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
                                         'stop-undefine')

            # STEP 7
            self.run_libvirt_service_cmd(self.primary_node, vm_service_name,
                                         'force-stop-undefine')

        finally:
            self.remove_item(self.primary_node, self.images_dir +
                             '/{0}'.format(self.temp_image),
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
