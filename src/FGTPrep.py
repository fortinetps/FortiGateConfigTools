import re
import sys
import uuid
import shlex
import getopt
import portion
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
	with open(path) as f:
		conf = Parser()
		conf.parse_text(f)
		return conf.section_dict

def str2ranglist(rs):
    try:
        rl = [(range(int(r.split(':')[0].split('-')[0]), int(r.split(':')[0].split('-')[1]) + 1) if '-' in r.split(':')[0] else range(int(r.split(':')[0]), int(r.split(':')[0]) + 1) ,
range(int(r.split(':')[1].split('-')[0]), int(r.split(':')[1].split('-')[1]) +1) if '-' in r.split(':')[1] else range(int(r.split(':')[1]), int(r.split(':')[1]) + 1)) if ':' in r else 
(range(int(r.split('-')[0]), int(r.split('-')[1]) + 1) if '-' in r else range(int(r), int(r) + 1) , range(1,65536)) for r in rs.split(' ')]
    except ValueError:
        return []
    else:
        return rl

def process_config(config):
    # make sure all the required configuration sections exist
    if config.get('config firewall address') and config.get('config firewall addrgrp') and config.get('config firewall service custom') and config.get('config firewall service group') and config.get('config firewall policy'):
        # create the corresponding flatten sections
        config['config firewall address flatten'] = defaultdict(f)
        config['config firewall addrgrp flatten'] = defaultdict(f)
        config['config firewall service custom flatten'] = defaultdict(f)
        config['config firewall service group flatten'] = defaultdict(f)
        config['config firewall policy flatten'] = defaultdict(f)

        # flatten config firewall address (only for subnet and iprannge)
        for name, value in config['config firewall address'].items():
            if 'set subnet' in value:
                ipaddr0 = ipaddress.IPv4Network(value['set subnet'][0].replace(' ','/'))
                config['config firewall address flatten'][name] = range(int(ipaddr0[0]), int(ipaddr0[-1]) + 1)
            elif 'set start-ip' in value:
                ipaddr1 = ipaddress.ip_network(value['set start-ip'][0])
                ipaddr2 = ipaddress.ip_network(value['set end-ip'][0])
                config['config firewall address flatten'][name] = range(int(ipaddr1[0]), int(ipaddr2[0]) + 1)
            else:
                config['config firewall address flatten'][name] = range(0, 2^32)

        # flatten config firewall addrgrp
        for name, value in config['config firewall addrgrp'].items():
            member_list = shlex.split(value['set member'][0])
            # flatten nested addrgrp member if exists
            addrgrp_member = True
            while addrgrp_member:
                addrgrp_member = False
                for member in member_list:
                    if member in config['config firewall addrgrp'].items():
                        addrgrp_member = True
                        member_list.remove(member)
                        member_list.extend(shlex.split(config['config firewall addrgrp'][member]['set member'][0]))
                        break

            # convert member list to list of ranges
            config['config firewall addrgrp flatten'][name] = [config['config firewall address flatten']['edit "{}"'.format(member)] for member in member_list]

        # flatten config firewall service custom (only for tcp/udp/icmp)
        for name, value in config['config firewall address'].items():
            if 'set tcp-portrange' in value or 'set udp-portrange' in value:
                tcp_range_list = str2ranglist(value.get('set tcp-portrange', [''])[0])
                udp_range_list = str2ranglist(value.get('set udp-portrange', [''])[0])
                config['config firewall address flatten'][name]['tcp range list'] = tcp_range_list
                config['config firewall address flatten'][name]['udp range list'] = udp_range_list
            elif 'set protocol' in value and 'ICMP' in value['set protocol']:
                icmp_type = value.get('set icmptype', ['0'])[0]
                icmp_code = value.get('set icmpcode', ['0'])[0]
                config['config firewall address flatten'][name]['icmp type'] = icmp_type
                config['config firewall address flatten'][name]['icmp code'] = icmp_code
            else:
                # config['config firewall address flatten'][name] = range(0, 2^32)

            
            # flatten_member_list = []
            # set_member = shlex.split(cp_global_config.get(search_addrgrp, {}).get('edit "{}"'.format(address))['set member'][0])


opts, args = getopt.getopt(sys.argv[1:],'hvi:g:p:', ['help'])
version = '20220713'
fgt_folder = ''
fmg_global = ''
output_prefix = 'fmg'
verbose = False

for opt, arg in opts:
    if opt in ('-h', '--help'):
        print('***********************************************************************************')
        print('Usage: python FGTPrep.py -i <FGT configuration folder> -g <FMG global file> -p <Output Prefix>')
        print('')
        print('***********************************************************************************')
    elif opt == '-v':
        verbose = True
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
config_all = parse_file(fgt_path / 'config-all.txt')
process_config(config_all)

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
                local_objects[section][section][k] = v
    combined_file = fgt_path / '{}-{}.txt'.format(output_prefix, '-'.join(section.split(' ')))
    original_stdout = sys.stdout
    with open(combined_file.resolve(), 'w') as output:
        sys.stdout = output
        niceprint(local_objects[section], indent=1)
        sys.stdout = original_stdout

# convert/flatten srcaddr/dstaddr/service to list of ranges
# for better check the if one policy shadow/cover another
firewall_policy_flatten = defaultdict(f)
for pol_id, pol in local_objects['config firewall policy']['config firewall policy'].items():
    if not pol_id.startswith('comment'): # skip comment
        firewall_policy_flatten[pol_id] = flatten(pol)

# fixing/preparing firewall policy
# search firewall policy with - set global-label "Firewall Management"
# and comment out this policy
new_config_firewall_policy1 = defaultdict(f)
for pol_id, pol in local_objects['config firewall policy']['config firewall policy'].items():
    if not pol_id.startswith('comment'): # skip comment
        if pol.get('set global-label', [''])[0].startswith('"Firewall Management'):
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