import sys
import getopt

from collections import defaultdict
from pyfgtconflib import Parser
f = lambda: defaultdict(f)

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
        niceprint(d['config global'])
        print ('end')

        for k, v in d['config vdom'].items():
            print ('')
            print ('config vdom')
            print (k)
            niceprint(v)
            print ('end')
    else:
        for k, v in d.items():
            if isinstance(v, dict): # sub-section
                fields = k.strip().split(' ')
                method = fields[0]
                print ('{0}{1}'.format(empty_str.rjust(offset), ' '.join(fields)))  # print sub-section header
                niceprint(v, offset + indent)   # print sub-section
                if method == 'config':
                    print (empty_str.rjust(offset) + 'end')     # print sub-section footer
                elif method == 'edit':
                    print (empty_str.rjust(offset) + 'next')    # print sub-section footer
            else:                   # leaf
                if k == '':
                    return
                fields = k.strip().split(' ')
                if len(v):
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

def print_help():
    print('***********************************************************************************')
    print('Usage: python FGTSDWANMigration.py -f <Input FGT Configuration File> -o <Output FGT Configuration File> -z <SDWAN Zone List> -v <VDOM name>')
    print('')
    print("  -f <FGT Configuration File>")
    print("  -v <FGT Configuration File>")
    print("")
    print('  -d: debug/verbose mode')
    print('')
    print('***********************************************************************************')
    print('Examples:')
    print('  ppython FGTSDWANMigration.py -f test.conf')
    print('')
    print('***********************************************************************************')
    sys.exit(2)

vdom = ''
verbose = False
# parse args
if len(sys.argv) < 2:
    print_help()

try:
    opts, args = getopt.getopt(sys.argv[1:],'hdf:v:', ['help'])
except getopt.GetoptError as e:
    print_help()

for opt, arg in opts:
    if opt in ('-h', '--help'):
        print_help()
    elif opt == '-f':
        filename = arg
    elif opt == '-v':
        vdom = arg
    elif opt == '-d':
        verbose = True

config = parse_file(filename)
new_config = config

# check if VDOM is enabled
if len(config['config vdom']) == 1 and not vdom:
    new_config = list(config['config vdom'].items())[0]

if len(config['config vdom']) > 1:
    if not vdom:
        print('FGT have {} VDOMs:'.format(len(config['config vdom'])))
        for k, v in config['config vdom'].items():
            print(k.split(' ')[1])
        print('Please specify which VDOM you want SDWAN migration')
        print_help()
    else:
        vdom_list = []
        for k, v in config['config vdom'].items():
            vdom_list.append(k)
        k1 = 'edit ' + vdom
        if k1 not in vdom_list:
            print('Wrong FGT VDOM name specfied!')
            print('FGT have {} VDOMs:'.format(len(config['config vdom'])))
            for k, v in config['config vdom'].items():
                print(k.split(' ')[1])
            print('Please specify which VDOM you want SDWAN migration')
            print_help()
        else:
            new_config= config['config vdom'][k1]

# check if SDWAN is enabled
if 'enable' in new_config['config system sdwan']['set status']:
    if verbose:
        niceprint(new_config['config system sdwan'])
    print('FGT SDWAN is enabled already, no SDWAN migration is needed')
    # exit(0)

# check "config vpn ipsec phase1-interface" to determind underlay interface list
underlay_interface_list = []
overlay_interface_list = []
if (len(new_config['config vpn ipsec phase1-interface'])):
    for k, v in new_config['config vpn ipsec phase1-interface'].items():
        if v['set interface'][0] not in underlay_interface_list:
            underlay_interface_list.append(v['set interface'][0])
        overlay_interface_list.append(k.split(' ')[1])
else:
    print('FGT has 0 VPN phase1 configuration, no SDWAN migration is needed')
if verbose:
    print('Underlay Interface List:\n{}'.format(underlay_interface_list))
    print('Overlay Interface List:\n{}'.format(overlay_interface_list))

if not len(overlay_interface_list):
    print('FGT has no VPN configured, not able to get underlay/overlay interface list, please check')
    exit(0)

# create sdwan zone
# new_config['config system sdwan']['set status'] = defaultdict(f)
new_config['config system sdwan']['set status'] = ['enable']
new_config['config system sdwan']['config zone']['edit underlay']
new_config['config system sdwan']['config zone']['edit overlay']

# create sdwan members
for idx, intf in enumerate(underlay_interface_list, 1):
    new_config['config system sdwan']['config member']['edit {}'.format(idx)]['set interface'] = [intf]
    new_config['config system sdwan']['config member']['edit {}'.format(idx)]['set zone'] = ['underlay']

for idx, intf in enumerate(overlay_interface_list, 10):
    new_config['config system sdwan']['config member']['edit {}'.format(idx)]['set interface'] = [intf]
    new_config['config system sdwan']['config member']['edit {}'.format(idx)]['set zone'] = ['overlay']


# create sdwan health-check

# create sdwan services

# check and fix firewall policy
for k, v in new_config['config firewall policy'].items():
    policy_srcintf_updated = False
    new_srcintf = []
    for intf in v['set srcintf']:
        if intf in underlay_interface_list:
            if intf not in new_srcintf:
                new_srcintf.append('underlay')
                policy_srcintf_updated = True
        elif intf in overlay_interface_list:
            if intf not in new_srcintf:
                new_srcintf.append('overlay')
                policy_srcintf_updated = True
        else:
            if intf not in new_srcintf:
                new_srcintf.append(intf)

    policy_dstintf_updated = False
    new_dstintf = []
    for intf in v['set dstintf']:
        if intf in underlay_interface_list:
            if intf not in new_dstintf:
                new_dstintf.append('underlay')
                policy_dstintf_updated = True
        elif intf in overlay_interface_list:
            if intf not in new_dstintf:
                new_dstintf.append('overlay')
                policy_dstintf_updated = True
        else:
            if intf not in new_dstintf:
                new_dstintf.append(intf)

    if policy_srcintf_updated:
        new_config['config firewall policy'][k]['set srcintf'] = new_srcintf

    if policy_dstintf_updated:
        new_config['config firewall policy'][k]['set dstintf'] = new_dstintf

# check and fix router static
new_config['config router static']['edit 0']['set sdwan'] = ['enable']
new_config['config router static']['edit 0']['set distance'] = ['1']

# check and fix link-monitor

# check other underlay/overlay references

# check
if verbose:
    niceprint(new_config['config system sdwan'])
    niceprint(new_config['config firewall policy'])
    niceprint(new_config['config router static'])
