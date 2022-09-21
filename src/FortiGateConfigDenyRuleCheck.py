import re
import sys
import copy
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


def port2portion(rs):   # ignore_source
    try:
        pl = [portion.closedopen(int(r.split(':')[0].split('-')[0]), int(r.split(':')[0].split('-')[1]) + 1) if '-' in r.split(':')[0] else portion.closedopen(int(r.split(':')[0]), int(r.split(':')[0]) + 1) if ':' in r else 
portion.closedopen(int(r.split('-')[0]), int(r.split('-')[1]) + 1) if '-' in r else portion.closedopen(int(r), int(r) + 1) for r in rs.split(' ')]
    except ValueError:
        return portion.empty()
    else:
        pr = portion.empty()
        for p in pl:
            pr = pr.union(p)
        return pr

def interface_intersection(intf1, intf2):
    if '"any"' in intf1:
        return intf2
    elif '"any"' in intf2:
        return intf1
    else:
        return list(set(intf1) & set(intf2))


def address_intersection(addr1, addr2, addr1_f, addr2_f):
    if '"all"' in addr1:
        return addr2
    elif '"all"' in addr2:
        return addr1
    else:
        return addr1_f.intersection(addr2_f)


def service_intersection(serv1, serv2, serv1_f, serv2_f):
    if '"ALL"' in serv1:
        return serv2
    elif '"ALL"' in serv2:
        return serv1
    else:
        return {k: serv1_f[k] & serv2_f[k] for k in [k for k in serv1_f if serv1_f [k]!=serv1_f.default_factory()]}

def policy_intersection(pol1_id, pol2_id, pol1, pol2, pol1_f, pol2_f):
    srcintf = interface_intersection(pol1['set srcintf'], pol2['set srcintf'])
    if not srcintf:
        print('{} ^ {} => srcintf intersection is empty'.format(pol1_id, pol2_id))
        return

    dstintf = interface_intersection(pol1['set dstintf'], pol2['set dstintf'])
    if not dstintf:
        print('{} ^ {} => sdstintf intersection is empty'.format(pol1_id, pol2_id))
        return

    srcaddr = address_intersection(pol1['set srcaddr'], pol2['set srcaddr'], pol1_f['set srcaddr'], pol2_f['set srcaddr'])
    if not srcaddr:
        print('{} ^ {} => srcaddr intersection is empty'.format(pol1_id, pol2_id))
        return

    dstaddr = address_intersection(pol1['set dstaddr'], pol2['set dstaddr'], pol1_f['set dstaddr'], pol2_f['set dstaddr'])
    if not dstaddr:
        print('{} ^ {} => dstaddr intersection is empty'.format(pol1_id, pol2_id))
        return

    service = service_intersection(pol1['set service'], pol2['set service'], pol1_f['set service'], pol2_f['set service'])
    if (not service) or (type(service) == dict and ((not service['tcp range list']) and (not service['udp range list']) and (not service['icmp type']))):
        print('{} ^ {} => service intersection is empty'.format(pol1_id, pol2_id))
        return

    print('{} ^ {} => srcintf:{}, dstintf:{}, srcaddr:{}, dstaddr:{}, service:{}'.format(pol1_id, pol2_id, srcintf, dstintf, srcaddr, dstaddr, service))
    return True

def parse_file(path):
	with open(path, encoding='utf-8-sig') as f:
		conf = Parser()
		conf.parse_text(f)
		return conf.section_dict


opts, args = getopt.getopt(sys.argv[1:],'hvi:', ['help', 'vdom='])
version = '20220920'
fgt_config_file = ''
fgt_vdom = ''
verbose = False


for opt, arg in opts:
    if opt in ('-h', '--help'):
        print('***********************************************************************************')
        print('Usage: python FortiGateConfigDenyRuleCheck.py -i FortiGate_Config_File')
        print('')
        print('***********************************************************************************')
        exit(0)
    elif opt == '-v':
        verbose = True
    elif opt == '-i':
        fgt_config_file = arg
    elif opt == '--vdom':
        fgt_vdom = arg

fgt_path = Path(fgt_config_file)
if not fgt_path.is_file:
    print('Please check and specify correct FGT configuration file')
    exit(2)

# load FortiGate Config File, assume there is not vdom
config_all = parse_file(fgt_path)

# config "root"
if fgt_vdom and 'vdom' in config_all and fgt_vdom in config_all['vdom']:
    config_root = config_all['vdom'][fgt_vdom]
elif not fgt_vdom:
    config_root = config_all
else:
    print('No vdom {} found in FortiGate Configuration File, please check ...'.format(fgt_vdom))
    exit(2)

# flatten firewall address
if 'config firewall address' in config_root:
    config_address = config_root['config firewall address']
    config_address_flatten = defaultdict(f)
    # flatten config firewall address (only for subnet, iprannge and type:value)
    for name, value in config_address.items():
        if 'set subnet' in value:
            ipaddr0 = ipaddress.IPv4Network(value['set subnet'][0].replace(' ','/'))
            config_address_flatten[name] = portion.closedopen(int(ipaddr0[0]), int(ipaddr0[-1]) + 1)
        elif 'set start-ip' in value:
            ipaddr1 = ipaddress.ip_network(value['set start-ip'][0])
            ipaddr2 = ipaddress.ip_network(value['set end-ip'][0])
            config_address_flatten[name] = portion.closedopen(int(ipaddr1[0]), int(ipaddr2[0]) + 1)
        else:
            config_address_flatten[name] = ':'.join(value['set type'][0], value['set fqdn'][0])

else:
    print('No "config firewall address" in FortiGate Configuration File, please check ...')
    exit(2)

# flatten firewall addrgrp
if 'config firewall addrgrp' in config_root:
    config_addrgrp = config_root['config firewall addrgrp']
    config_addrgrp_flatten = defaultdict(f)
    # flatten config firewall addrgrp
    for name, value in config_addrgrp.items():
        member_list = shlex.split(value['set member'][0])
        # flatten nested addrgrp member if exists
        addrgrp_member = True
        while addrgrp_member:
            addrgrp_member = False
            for member in member_list:
                if 'edit "{}"'.format(member) in config_addrgrp:
                    addrgrp_member = True
                    member_list.extend(shlex.split(config_addrgrp['edit "{}"'.format(member)]['set member'][0]))
                    break
            if addrgrp_member:
                member_list.remove(member)

        # convert member list to list of ranges
        pl = [config_address_flatten['edit "{}"'.format(member)] for member in member_list]
        pr = portion.empty()
        for p in pl:
            pr = pr.union(p)
        config_addrgrp_flatten[name] = pr

# flatten firewall service custom
if 'config firewall service custom' in config_root:
    config_service = config_root['config firewall service custom']
    config_service_flatten = defaultdict(f)
    # flatten config firewall service custom (only for tcp/udp/icmp)
    for name, value in config_service.items():
        if 'set tcp-portrange' in value or 'set udp-portrange' in value:
            tcp_range_list = port2portion(value.get('set tcp-portrange', [''])[0])
            udp_range_list = port2portion(value.get('set udp-portrange', [''])[0])
            config_service_flatten[name]['tcp range list'] = tcp_range_list
            config_service_flatten[name]['udp range list'] = udp_range_list
        elif 'set protocol' in value and 'ICMP' in value['set protocol']:
            icmp_type = value.get('set icmptype', ['0'])[0]
            # icmp_code = value.get('set icmpcode', ['0'])[0]
            config_service_flatten[name]['icmp type'] = portion.singleton(int(icmp_type))
        else:
            config_service_flatten[name]['tcp range list'] = portion.closedopen(1, 65536)
            config_service_flatten[name]['udp range list'] = portion.closedopen(1, 65536)
            config_service_flatten[name]['icmp type'] = portion.singleton(0)

else:
    print('No "config firewall service custom" in FortiGate Configuration File, please check ...')
    exit(2)

# flatten firewall service group
if 'config firewall service group' in config_root:
    config_servgrp = config_root['config firewall service group']
    config_servgrp_flatten = defaultdict(f)
    # flatten config firewall service group
    for name, value in config_servgrp.items():
        member_list = shlex.split(value['set member'][0])
        # flatten nested servgrp member if exists
        servgrp_member = True
        while servgrp_member:
            servgrp_member = False
            for member in member_list:
                if 'edit "{}"'.format(member) in config_servgrp.items():
                    servgrp_member = True
                    member_list.remove(member)
                    member_list.extend(shlex.split(config_servgrp['edit "{}"'.format(member)]['set member'][0]))
                    break

        # convert member list to list of ranges
        tpl = [config_service_flatten['edit "{}"'.format(member)].get('tcp range list', portion.empty()) for member in member_list]
        upl = [config_service_flatten['edit "{}"'.format(member)].get('udp range list', portion.empty()) for member in member_list]
        ipl = [config_service_flatten['edit "{}"'.format(member)].get('icmp type', portion.empty()) for member in member_list]
        pr = portion.empty()
        for p in tpl:
            pr = pr.union(p)
        config_servgrp_flatten[name]['tcp range list'] = pr
        pr = portion.empty()
        for p in upl:
            pr = pr.union(p)
        config_servgrp_flatten[name]['udp range list'] = pr
        pr = portion.empty()
        for p in ipl:
            pr = pr.union(p)
        config_servgrp_flatten[name]['icmp type'] = pr

# flatten firewall policy
if 'config firewall policy' in config_root:
    config_policy = config_root['config firewall policy']
    config_policy_flatten = defaultdict(f)
    # flatten config firewall policy
    for name, value in config_policy.items():
        if not name.startswith('comment'): # skip comment
            pol = defaultdict(f)
            pol = copy.copy(value)

            # flatten "set srcaddr"
            srcaddr_list = shlex.split(value['set srcaddr'][0])
            srcaddr_flatten = portion.empty()
            for addr in srcaddr_list:
                srcaddr_flatten = srcaddr_flatten.union(config_address_flatten.get('edit "{}"'.format(addr), portion.empty()))
                srcaddr_flatten = srcaddr_flatten.union(config_addrgrp_flatten.get('edit "{}"'.format(addr), portion.empty()))
            pol['set srcaddr'] = srcaddr_flatten

            # flatten "set dstaddr"
            dstaddr_list = shlex.split(value['set dstaddr'][0])
            dstaddr_flatten = portion.empty()
            for addr in dstaddr_list:
                dstaddr_flatten = dstaddr_flatten.union(config_address_flatten.get('edit "{}"'.format(addr), portion.empty()))
                dstaddr_flatten = dstaddr_flatten.union(config_addrgrp_flatten.get('edit "{}"'.format(addr), portion.empty()))
            pol['set dstaddr'] = dstaddr_flatten

            # flatten "set service"
            service_list = shlex.split(value['set service'][0])
            tcp_flatten = portion.empty()
            udp_flatten = portion.empty()
            icmp_flatten = portion.empty()
            for service in service_list:
                tcp_flatten = tcp_flatten.union(config_service_flatten.get('edit "{}"'.format(service), {}).get('tcp range list', portion.empty()))
                tcp_flatten = tcp_flatten.union(config_servgrp_flatten.get('edit "{}"'.format(service), {}).get('tcp range list', portion.empty()))
                udp_flatten = udp_flatten.union(config_service_flatten.get('edit "{}"'.format(service), {}).get('udp range list', portion.empty()))
                udp_flatten = udp_flatten.union(config_servgrp_flatten.get('edit "{}"'.format(service), {}).get('udp range list', portion.empty()))
                icmp_flatten = icmp_flatten.union(config_service_flatten.get('edit "{}"'.format(service), {}).get('icmp type', portion.empty()))
                icmp_flatten = icmp_flatten.union(config_servgrp_flatten.get('edit "{}"'.format(service), {}).get('icmp type', portion.empty()))
            service_flatten = defaultdict(f)
            service_flatten['tcp range list'] = tcp_flatten
            service_flatten['udp range list'] = udp_flatten
            service_flatten['icmp type'] = icmp_flatten
            pol['set service'] = service_flatten
            
            config_policy_flatten[name] = pol

else:
    print('No "config firewall policy" in FortiGate Configuration File, please check ...')
    exit(2)

for pol1_id, pol1 in config_policy.items():
    if not pol1_id.startswith('comment'): # skip comment
        pol1_before_pol2 = False
        for pol2_id, pol2 in config_policy.items():
            if not pol2_id.startswith('comment'): # skip comment
                if pol2_id == pol1_id:  # when pol2 reach to pol1
                    pol1_before_pol2 = True
                    continue
                else:
                    if pol1_before_pol2:
                        policy_intersection(pol1_id, pol2_id, pol1, pol2, config_policy_flatten[pol1_id], config_policy_flatten[pol2_id])
                    else:
                        policy_intersection(pol2_id, pol1_id, pol2, pol1, config_policy_flatten[pol2_id], config_policy_flatten[pol1_id])

# niceprint(config_policy_flatten)