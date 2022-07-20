import re
import sys
import uuid
import shlex
import getopt
import ipaddress
from pathlib import Path
from collections import defaultdict
from functools import reduce

f = lambda: defaultdict(f)

def getFromDict(dataDict, mapList):
    return reduce(lambda d, k: d[k], mapList, dataDict)

def setInDict(dataDict, mapList, value):
    getFromDict(dataDict, mapList[:-1])[mapList[-1]] = value

class Parser(object):
    previous_set_headers = {}
    previous_set_values = {}

    def __init__(self):
        self.config_header = []
        self.section_dict = defaultdict(f)

	# parse "config"
    def parse_config(self, fields):
        self.config_header.append(' '.join(fields))

	# parse "edit"
    def parse_edit(self, line):
        self.config_header.append(' '.join(line))

	# parse "set" (key/value)
    def parse_set(self, line):
        values = []
        key = ' '.join([line[0], line[1]])
        values.append(' '.join(line[2:]))
        self.previous_set_values = values
        headers= self.config_header + [key]
        self.previous_set_headers = headers
        setInDict(self.section_dict, headers, values)

	# parse "set" (key/multiline value)
    def parse_set_multiline(self, line):
        self.previous_set_values.append(' '.join(line[0:]))
        setInDict(self.section_dict, self.previous_set_headers, self.previous_set_values)

	# parse "set" (key/value)
    def parse_comment(self, line):
        values = []
        key = ' '.join(['comment', str(uuid.uuid4())])
        values = line
        headers= self.config_header + [key]
        self.previous_set_headers = headers
        setInDict(self.section_dict, headers, values)

	# parse "unset" (key/no value)
    def parse_unset(self, line):
        key = ' '.join([line[0], line[1]])
        values = ' '.join(line[2:])
        headers= self.config_header + [key]
        self.previous_set_headers = headers
        setInDict(self.section_dict, headers, values)

	# parse "next" (for "config" or "edit")
    def parse_next(self, line):
        if not (set(self.config_header)).issubset(set(self.previous_set_headers)):
            if self.previous_set_headers == {} and self.config_header[0] == 'config vdom':
                getFromDict(self.section_dict, ['config global'])
            getFromDict(self.section_dict, self.config_header)
        if len(self.config_header) < 2:
            print("it seems like next here is incorrect")
        self.config_header.pop()

    # parse "end" (for "config" or "edit")
	# in multi vdom configuration, config vdom -> edit vdom_name -> end, without a next, which we need to handle it...
    def parse_end(self, line):
        if not (set(self.config_header)).issubset(set(self.previous_set_headers)):
            getFromDict(self.section_dict, self.config_header)
        if (set(self.config_header)).issubset(set(self.previous_set_headers)) and len(self.config_header) == 2 and self.config_header[0] == 'config vdom':
            self.config_header.pop()    # we need this 2nd pop to close the config vdom wihout next properly
        self.config_header.pop()

	# prase FortiGate configuration
    def parse_text(self, text):
        gen_lines = (line.rstrip() for line in text if line.strip())
        previous_method = None
        for line in gen_lines:
            # if line == 'config user radius':
            #     print('here')
            fields = line.strip().split(' ')

            valid_fields= ['config', 'edit', 'set', 'unset', 'next', 'end']
            if fields[0] in valid_fields:
                method = fields[0]
                previous_method = method
                # call parse function according to the verb
                getattr(Parser, 'parse_' + method)(self, fields)
            elif re.match(r'^\s*#.*', line):    # parse comment, you need to parse this before parse multiline value next
                # but this might cause issue if multiline value happen to startswith a '#' sign
                # multiline value could be detected by checking if previous line value starts with single or double quotes
                # will need more time to work on this ....
                method = 'comment'
                previous_method = method
                # call parse function according to the verb
                getattr(Parser, 'parse_' + method)(self, [line])
            elif previous_method == 'set':      # parse multiline value in set
                getattr(Parser, 'parse_' + 'set_multiline')(self, fields)

        return self.section_dict

empty_str = ''
def niceprint(d, offset = 0, indent = 4):
    if d.get('config global') and d.get('config vdom'):
        for k, v in d.items():
            if v == {}:
                print (k)
        print ('')
        print ('config vdom')
        for k, _ in d['config vdom'].items():
            print (k)
            print ('next')
        print ('end')

        print ('')
        print ('config global')
        niceprint(d['config global'], indent=indent)
        print ('end')

        for k, v in d['config vdom'].items():
            print ('')
            print ('config vdom')
            print (k)
            niceprint(v, indent=indent)
            print ('end')
    else:
        for k, v in d.items():
            if isinstance(v, dict): # sub-section
                fields = k.strip().split(' ')
                method = fields[0]
                print ('{0}{1}'.format(empty_str.rjust(offset), ' '.join(fields)))  # print sub-section header
                niceprint(v, offset + indent, indent=indent)   # print sub-section
                if method == 'config':
                    print (empty_str.rjust(offset) + 'end')     # print sub-section footer
                elif method == 'edit':
                    print (empty_str.rjust(offset) + 'next')    # print sub-section footer
            else:                   # leaf
                if k == '':
                    return
                fields = k.strip().split(' ')
                if len(v):
                    if fields[0] == 'comment':  # for comment
                        print ('{}'.format(v[0]))
                    else:
                        print ('{0}{1} {2}'.format(empty_str.rjust(offset), ' '.join(fields), v[0]))    # print value
                        for xx in range(1, len(v)):     # print multiline value if exists
                            print (v[xx] + '\r')
                else:
                    print ('{0}{1}'.format(empty_str.rjust(offset), ' '.join(fields)))  # print unset without value

def parse_file(path):
	with open(path, encoding='utf-8-sig') as f:
		conf = Parser()
		conf.parse_text(f)
		return conf.section_dict

opts, args = getopt.getopt(sys.argv[1:],'hvi:g:p:', ['help', 'setmember'])
version = '20220719'
fgt_folder = ''
fmg_global = ''
output_prefix = 'fmg'
set_member = False  # for addrgrp/service group, use "append member" by default
verbose = False

for opt, arg in opts:
    if opt in ('-h', '--help'):
        print('***********************************************************************************')
        print('Usage: python FGTPrep.py -i <FGT configuration folder> -g <FMG global file> -p <Output Prefix>')
        print('')
        print('***********************************************************************************')
        exit(0)
    elif opt == '-v':
        verbose = True
    elif opt == '--setmember':
        set_member = True
    elif opt == '-i':
        fgt_folder = arg
    elif opt == '-g':
        fmg_global = arg
    elif opt == '-p':
        output_prefix = arg

fgt_path = Path(fgt_folder)
fmg_path = Path(fmg_global)
if not fgt_path.is_dir:
    print('Please check and specify correct FGT configuration folder')
    exit(2)
if not fmg_path.is_file:
    print('Please check and specify correct FMG configuration file')
    exit(2)

# load config-all.txt
# config_all = parse_file(fgt_path / 'config-all.txt')

section_list = ['config firewall address', 'config firewall addrgrp', 'config firewall service custom', 'config firewall service group', 'config firewall policy']
filter_list = ['-'.join(x.split(' ')) for x in section_list]
# filter those configuration files we are intersted in
fgt_files = [x for x in fgt_path.glob('*.txt') if x.is_file() and re.match(r'^\d+-({})(-\d+)*$'.format('|'.join(filter_list)), x.stem)]
if not fgt_files:   # if there is no FGT files in the folder, return error
    print('Please check and specify correct FGT configuration folder')
    exit(2)

# to combine
local_objects = defaultdict(f)
for section in section_list:
    local_objects[section] = defaultdict(f)
    for file in fgt_files:
        if '-'.join(section.split(' ')) in file.stem:
            section_config = parse_file(file.resolve())
            for k, v in section_config[section].items():
                if not set_member and 'set member' in v:    # change "set member" to "append member"
                    v['append member'] = v['set member']
                    del v['set member']
                local_objects[section][section][k] = v
    combined_file = fgt_path / '{}-{}.txt'.format(output_prefix, '-'.join(section.split(' ')))
    original_stdout = sys.stdout
    with open(combined_file.resolve(), 'w') as output:
        sys.stdout = output
        niceprint(local_objects[section], indent=1)
        sys.stdout = original_stdout

# fixing/preparing firewall policy
# search firewall policy with - set global-label "Firewall Management"
# and comment out this policy
new_config_firewall_policy1 = defaultdict(f)
for pol_id, pol in local_objects['config firewall policy']['config firewall policy'].items():
    if not pol_id.startswith('comment'): # skip comment
        # after exam some converted policy, it seems to me we only need to comment those "Firewall Management" policy
        # if the srcintf == dstintf and srcaddr == dstaddr
        if (pol.get('set global-label', [''])[0].startswith('"Firewall Management') and 
        pol.get('set srcintf', ['']) == pol.get('set dstintf', ['']) and
        pol.get('set srcaddr', ['']) == pol.get('set dstaddr', [''])):
            new_config_firewall_policy1[' '.join(['comment', str(uuid.uuid4())])] = ['#{}'.format(pol_id)]
            for k1, v1 in pol.items():
                if k1.startswith('comment'):    # already a comment
                    new_config_firewall_policy1[k1] = v1
                else:    
                    new_config_firewall_policy1[' '.join(['comment', str(uuid.uuid4())])] = ['# {} {}'.format(k1, v1[0])]
            new_config_firewall_policy1[' '.join(['comment', str(uuid.uuid4())])] = ['#{}'.format('next')]
        else:
            new_config_firewall_policy1[pol_id] = pol
    else:
        new_config_firewall_policy1[pol_id] = pol

# add "set logtraffic-start enable" if "set logtraffic all" exists
# add "set utm-status enable"
# add "set profile-type group"
# add "set profile-group "g.JPMC.SecProf""
for pol_id, pol in new_config_firewall_policy1.items():
    if not pol_id.startswith('comment'): # skip comment
        if pol.get('set logtraffic', [''])[0] == 'all':
            pol['set logtraffic-start'] = ['enable']
            pol['set utm-status']       = ['enable']
            pol['set profile-type']     = ['group']
            pol['set profile-group']    = ['"g.JPMC.SecProf"']

# find deny policies (mostly 2 of them but could be more), and comment out the last one and move other to the bottom
new_config_firewall_policy2 = defaultdict(f)
for pol_id, pol in new_config_firewall_policy1.items():
    if not pol_id.startswith('comment'): # skip comment
        if pol.get('set action', [''])[0] != 'deny':
            new_config_firewall_policy2[pol_id] = pol
    else:
        new_config_firewall_policy2[pol_id] = pol

last_deny_pol = ()
for pol in list(new_config_firewall_policy1.items())[::-1]:
    if not pol[0].startswith('comment'): # skip comment
        if pol[1].get('set action', [''])[0] == 'deny':
            last_deny_pol = pol
            break

if last_deny_pol:
    for pol_id, pol in new_config_firewall_policy1.items():
        if not pol_id.startswith('comment'): # skip comment
            if pol.get('set action', [''])[0] == 'deny':
                if pol_id != last_deny_pol[0]:  # not last deny policy
                    new_config_firewall_policy2[pol_id] = pol
                else:   # last deny policy
                    new_config_firewall_policy2[' '.join(['comment', str(uuid.uuid4())])] = ['#{}'.format(pol_id)]
                    for k1, v1 in pol.items():
                        if k1.startswith('comment'):    # already a comment
                            new_config_firewall_policy2[k1] = v1
                        else:    
                            new_config_firewall_policy2[' '.join(['comment', str(uuid.uuid4())])] = ['# {} {}'.format(k1, v1[0])]
                    new_config_firewall_policy2[' '.join(['comment', str(uuid.uuid4())])] = ['#{}'.format('next')]

firewall_policy_fix = fgt_path / '{}-{}-fix.txt'.format(output_prefix, '-'.join('config firewall policy'.split(' ')))
original_stdout = sys.stdout
with open(firewall_policy_fix.resolve(), 'w') as output:
    sys.stdout = output
    niceprint({'config firewall policy': new_config_firewall_policy2}, indent=1)
    sys.stdout = original_stdout

# check FMG global object additions
# first, get all address (including addrgrp) and service (including service group) objects referenced in firewall policies
fgt_address_list = []
fgt_service_list = []
for pol_id, pol in new_config_firewall_policy2.items():
    if not pol_id.startswith('comment'): # skip comment
        set_srcaddr = shlex.split(pol.get('set srcaddr', [''])[0])
        set_dstaddr = shlex.split(pol.get('set dstaddr', [''])[0])
        set_service = shlex.split(pol.get('set service', [''])[0])
        fgt_address_list.extend(set_srcaddr)
        fgt_address_list.extend(set_dstaddr)
        fgt_service_list.extend(set_service)

fgt_address_list = list(sorted(set(fgt_address_list)))
fgt_address_set = set(fgt_address_list)
fgt_address_set.discard('all')
fgt_address_list = list(fgt_address_set)
fgt_service_list = list(sorted(set(fgt_service_list)))
fgt_service_set = set(fgt_service_list)
fgt_service_set.discard('ALL')
fgt_service_list = list(fgt_service_set)

# second, find definition in local configuration files
# if not found, check FMG global export
raw_global_config = parse_file(fmg_path.resolve())
fmg_global_config = raw_global_config.get('config vdom', {}).get('edit FortiGate', {})
if not fmg_global_config:
    fmg_global_config = raw_global_config
# if not found, check CP global from convert file and add to FMG object addition
search_address = 'config firewall address'
search_addrgrp = 'config firewall addrgrp'
missing_address = []
for address in fgt_address_list:
    if local_objects[search_address].get(search_address, {}).get('edit "{}"'.format(address)):
        continue
    if local_objects[search_addrgrp].get(search_addrgrp, {}).get('edit "{}"'.format(address)):
        continue
    if fmg_global_config.get(search_address, {}).get('edit "{}"'.format(address)):
        continue
    if fmg_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(address)):
        continue
    if local_objects[search_address].get(search_address, {}).get('edit {}'.format(address)):
        continue
    if local_objects[search_addrgrp].get(search_addrgrp, {}).get('edit {}'.format(address)):
        continue
    if fmg_global_config.get(search_address, {}).get('edit {}'.format(address)):
        continue
    if fmg_global_config.get(search_addrgrp, {}).get('edit {}'.format(address)):
        continue
    missing_address.append(address)
    print('missing address object: {}'.format(address))

search_servcus = 'config firewall service custom'
search_servgrp = 'config firewall service group'
missing_service = []
for service in fgt_service_list:
    if local_objects[search_servcus].get(search_servcus, {}).get('edit "{}"'.format(service)):
        continue
    if local_objects[search_servgrp].get(search_servgrp, {}).get('edit "{}"'.format(service)):
        continue
    if fmg_global_config.get(search_servcus, {}).get('edit "{}"'.format(service)):
        continue
    if fmg_global_config.get(search_servgrp, {}).get('edit "{}"'.format(service)):
        continue
    if local_objects[search_servcus].get(search_servcus, {}).get('edit {}'.format(service)):
        continue
    if local_objects[search_servgrp].get(search_servgrp, {}).get('edit {}'.format(service)):
        continue
    if fmg_global_config.get(search_servcus, {}).get('edit {}'.format(service)):
        continue
    if fmg_global_config.get(search_servgrp, {}).get('edit {}'.format(service)):
        continue
    missing_service.append(service)
    print('missing service object: {}'.format(service))

cp_glogal_path = fgt_path / 'config-all-global.txt'
cp_global_config = parse_file(cp_glogal_path.resolve())
fmg_global_additions = defaultdict(f)
if missing_address or missing_service:
    print('We need global additions...')
    cp_glogal_path = fgt_path / 'config-all-global.txt'
    cp_global_config = parse_file(cp_glogal_path.resolve())
    if missing_address:
        fmg_global_additions[search_address]    # touch "config firewall address" section

        # find missing addrgrp object first
        for address in missing_address:
            if cp_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(address)):
                fmg_global_additions[search_addrgrp]['edit "{}"'.format(address)] = cp_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(address))

        # we need to calcuate and flatern addrgrp (could be nested) to leaf address object
        more_addrgrp = True
        while more_addrgrp:
            more_addrgrp = False
            for address in missing_address:
                if cp_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(address)):
                    more_addrgrp = True
                    missing_address.remove(address)
                    set_member = shlex.split(cp_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(address))['set member'][0])
                    missing_address.extend(set_member)
        missing_address = list(sorted(set(missing_address)))
        
        # then find all missing address object
        for address in missing_address:
            if cp_global_config.get(search_address, {}).get('edit "{}"'.format(address)):
                fmg_global_additions[search_address]['edit "{}"'.format(address)] = cp_global_config.get(search_address, {}).get('edit "{}"'.format(address))
        # print('Something wrong, can not find defination of address:{}'.format(address))

    if missing_service:
        fmg_global_additions[search_servcus]    # touch "config firewall service custom" section

        # find missing addrgrp object first
        for service in missing_service:
            if cp_global_config.get(search_servgrp, {}).get('edit "{}"'.format(service)):
                fmg_global_additions[search_servgrp]['edit "{}"'.format(service)] = cp_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(service))

        # we need to calcuate and flatern addrgrp (could be nested) to leaf address object
        more_servgrp = True
        while more_servgrp:
            more_servgrp = False
            for service in missing_service:
                if cp_global_config.get(search_servgrp, {}).get('edit "{}"'.format(service)):
                    more_servgrp = True
                    missing_service.remove(service)
                    set_member = shlex.split(cp_global_config.get(search_servgrp, {}).get('edit "{}"'.format(service))['set member'][0])
                    missing_service.extend(set_member)
        missing_service = list(sorted(set(missing_service)))
        
        # then find all missing service custom object
        for service in missing_service:
            if cp_global_config.get(search_servcus, {}).get('edit "{}"'.format(service)):
                fmg_global_additions[search_servcus]['edit "{}"'.format(service)] = cp_global_config.get(search_servcus, {}).get('edit "{}"'.format(service))
        # print('Something wrong, can not find defination of service:{}'.format(service))

    global_addition_path = fgt_path / '{}-global-additions.txt'.format(output_prefix)
    original_stdout = sys.stdout
    with open(global_addition_path.resolve(), 'w') as output:
        sys.stdout = output
        niceprint(fmg_global_additions, indent=1)
        sys.stdout = original_stdout
else:
    print('All good and no global additions')
    exit(0)