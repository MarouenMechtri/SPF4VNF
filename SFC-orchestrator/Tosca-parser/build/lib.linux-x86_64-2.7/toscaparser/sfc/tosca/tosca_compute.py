#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import logging
from toscaparser.utils.validateutils import TOSCAVersionProperty
import toscaparser.sfcommon.utils
from toscaparser.sfc.syntax.hot_resource import HotResource
log = logging.getLogger('tosca')

# Name used to dynamically load appropriate map class.
TARGET_CLASS_NAME = 'ToscaCompute'


# A design issue to be resolved is how to translate the generic TOSCA server
# properties to OpenStack flavors and images.  At the Atlanta design summit,
# there was discussion on using Glance to store metadata and Graffiti to
# describe artifacts.  We will follow these projects to see if they can be
# leveraged for this TOSCA translation.
# For development purpose at this time, we temporarily hardcode a list of
# flavors and images here
FLAVORS = {'m1.xlarge': {'mem_size': 16384, 'disk_size': 160, 'num_cpus': 8},
           'm1.large': {'mem_size': 8192, 'disk_size': 80, 'num_cpus': 4},
           'm1.medium': {'mem_size': 4096, 'disk_size': 40, 'num_cpus': 2},
           'm1.small': {'mem_size': 2048, 'disk_size': 20, 'num_cpus': 1},
           'm1.tiny': {'mem_size': 512, 'disk_size': 1, 'num_cpus': 1},
           'm1.micro': {'mem_size': 128, 'disk_size': 0, 'num_cpus': 1},
           'm1.nano': {'mem_size': 64, 'disk_size': 0, 'num_cpus': 1}}

IMAGES = {'ubuntu-14.04-x86_64': {'architecture': 'x86_64',
                                             'type': 'Linux',
                                             'distribution': 'Ubuntu',
                                             'version': '14.04'},
          'ubuntu-12.04-x86_64': {'architecture': 'x86_64',
                                                   'type': 'Linux',
                                                   'distribution': 'Ubuntu',
                                                   'version': '12.04'},
          'fedora-amd64-heat-config': {'architecture': 'x86_64',
                                       'type': 'Linux',
                                       'distribution': 'Fedora',
                                       'version': '18.0'},
          'F18-x86_64-cfntools': {'architecture': 'x86_64',
                                  'type': 'Linux',
                                  'distribution': 'Fedora',
                                  'version': '19'},
          'Fedora-x86_64-20-20131211.1-sda': {'architecture': 'x86_64',
                                              'type': 'Linux',
                                              'distribution': 'Fedora',
                                              'version': '20'},
          'TestVM': {'architecture': 'x86_64',
                                      'type': 'Linux',
                                      'distribution': 'CirrOS',
                                      'version': '0.3.1'},
          'cirros-0.3.2-x86_64-uec': {'architecture': 'x86_64',
                                      'type': 'Linux',
                                      'distribution': 'CirrOS',
                                      'version': '0.3.2'},
          'rhel-6.5-test-image': {'architecture': 'x86_64',
                                  'type': 'Linux',
                                  'distribution': 'RHEL',
                                  'version': '6.5'},
          'ubuntu-15.04-x86_64': {'architecture': 'x86_64',
                                  'type': 'Linux',
                                  'distribution': 'Ubuntu',
                                  'version': '15.04'},
          'SFC_Client': {'architecture': 'x86_64',
                                  'type': 'sfc_client',
                                  'distribution': 'Ubuntu',
                                  'version': '14.04'}}


class ToscaCompute(HotResource):
    '''Translate TOSCA node type tosca.nodes.Compute.'''

    toscatype = 'tosca.nodes.Compute'

    def __init__(self, nodetemplate):
        super(ToscaCompute, self).__init__(nodetemplate,
                                           type='OS::Nova::Server')
        # List with associated hot port resources with this server
        self.assoc_port_resources = []
        pass

    def handle_properties(self):
        self.properties = self.translate_compute_flavor_and_image(
            self.nodetemplate.get_capability('host'),
            self.nodetemplate.get_capability('os'))
        self.properties['user_data_format'] = 'SOFTWARE_CONFIG'
        # TODO(anyone): handle user key
        # hardcoded here for testing
        self.properties['key_name'] = 'marouen'

    # To be reorganized later based on new development in Glance and Graffiti
    def translate_compute_flavor_and_image(self,
                                           host_capability,
                                           os_capability):
        hot_properties = {}
        host_cap_props = {}
        os_cap_props = {}
        image = None
        flavor = None
        if host_capability:
            for prop in host_capability.get_properties_objects():
                host_cap_props[prop.name] = prop.value
            flavor = self._best_flavor(host_cap_props)
        if os_capability:
            for prop in os_capability.get_properties_objects():
                os_cap_props[prop.name] = prop.value
            image = self._best_image(os_cap_props)
        hot_properties['flavor'] = flavor
        hot_properties['image'] = image
        # TODO(anyone): consider adding the flavor or image as a template
        # parameter if no match is found.
        return hot_properties

    def _best_flavor(self, properties):
        # start with all flavors
        match_all = FLAVORS.keys()

        # TODO(anyone): Handle the case where the value contains something like
        # get_input instead of a value.
        # flavors that fit the CPU count
        cpu = properties.get('num_cpus')
        match_cpu = self._match_flavors(match_all, FLAVORS, 'num_cpus', cpu)

        # flavors that fit the mem size
        mem = properties.get('mem_size')
        if mem:
            mem = toscaparser.sfcommon.utils.MemoryUnit.convert_unit_size_to_num(
                mem, 'MB')
        match_cpu_mem = self._match_flavors(match_cpu, FLAVORS,
                                            'mem_size', mem)
        # flavors that fit the disk size
        disk = properties.get('disk_size')
        if disk:
            disk = toscaparser.sfcommon.utils.MemoryUnit.\
                convert_unit_size_to_num(disk, 'GB')
        match_cpu_mem_disk = self._match_flavors(match_cpu_mem, FLAVORS,
                                                 'disk_size', disk)
        # if multiple match, pick the flavor with the least memory
        # the selection can be based on other heuristic, e.g. pick one with the
        # least total resource
        if len(match_cpu_mem_disk) > 1:
            return self._least_flavor(match_cpu_mem_disk, FLAVORS, 'mem_size')
        elif len(match_cpu_mem_disk) == 1:
            return match_cpu_mem_disk[0]
        else:
            return None

    def _best_image(self, properties):
        match_all = IMAGES.keys()
        architecture = properties.get('architecture')
        match_arch = self._match_images(match_all, IMAGES,
                                        'architecture', architecture)
        type = properties.get('type')
        match_type = self._match_images(match_arch, IMAGES, 'type', type)
        distribution = properties.get('distribution')
        match_distribution = self._match_images(match_type, IMAGES,
                                                'distribution',
                                                distribution)
        version = properties.get('version')
        version = TOSCAVersionProperty(version).get_version()
        match_version = self._match_images(match_distribution, IMAGES,
                                           'version', version)

        if len(match_version):
            return list(match_version)[0]

    def _match_flavors(self, this_list, this_dict, attr, size):
        '''Return from this list all flavors matching the attribute size.'''
        if not size:
            return list(this_list)
        matching_flavors = []
        for flavor in this_list:
            if isinstance(size, int):
                if this_dict[flavor][attr] >= size:
                    matching_flavors.append(flavor)
        return matching_flavors

    def _least_flavor(self, this_list, this_dict, attr):
        '''Return from this list the flavor with the smallest attr.'''
        least_flavor = this_list[0]
        for flavor in this_list:
            if this_dict[flavor][attr] < this_dict[least_flavor][attr]:
                least_flavor = flavor
        return least_flavor

    def _match_images(self, this_list, this_dict, attr, prop):
        if not prop:
            return this_list
        matching_images = []
        for image in this_list:
            if this_dict[image][attr].lower() == str(prop).lower():
                matching_images.append(image)
        return matching_images

    def get_hot_attribute(self, attribute, args):
        attr = {}
        # Convert from a TOSCA attribute for a nodetemplate to a HOT
        # attribute for the matching resource.  Unless there is additional
        # runtime support, this should be a one to one mapping.

        # Note: We treat private and public IP  addresses equally, but
        # this will change in the future when TOSCA starts to support
        # multiple private/public IP addresses.
        if attribute == 'private_address' or \
           attribute == 'public_address':
                ##############################################################
                ##                Modified by Marouen Mechtri               ##
                ##        @contacts: marouen.mechtri@it-sudparis.eu         ##
                ## @organization: Institut Mines-Telecom - Telecom SudParis ##
                ##############################################################
                attr['get_attr'] = [self.name, 'first_address']
                #attr['get_attr'] = [self.name, 'networks', 'private', 0]

        return attr
