import re
import uuid
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

config = parse_file('/workspaces/FortiGateConfigTools/temp/FGT/config-all.txt')

# search firewall policy with - set global-label "Firewall Management"
# and comment out this policy
new_config_firewall_policy = defaultdict(f)
for pol_id, pol in config['config firewall policy'].items():
    if not pol_id.startswith('comment'): # skip comment
        if pol.get('set global-label', [''])[0].startswith('"Firewall Management'):
            # print('Comment out this pol:{}'.format(pol_id))
            new_config_firewall_policy[' '.join(['comment', str(uuid.uuid4())])] = ['#{}'.format(pol_id)]
            for k1, v1 in pol.items():
                if k1.startswith('comment'):    # already a comment
                    new_config_firewall_policy[k1] = v1
                else:    
                    new_config_firewall_policy[' '.join(['comment', str(uuid.uuid4())])] = ['# {} {}'.format(k1, v1[0])]
            new_config_firewall_policy[' '.join(['comment', str(uuid.uuid4())])] = ['#{}'.format('next')]
            continue

    new_config_firewall_policy[pol_id] = pol
config['config firewall policy'] = new_config_firewall_policy

niceprint(config, indent=1)