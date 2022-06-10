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

config = parse_file('/workspaces/FortiGateConfigTools/temp/config-all.txt')
consolidated_polilies_p1 = defaultdict(f)
print('phase1 consolidation by combining services')
for key1, pol1 in config['config vdom']['edit "root"']['config firewall policy'].items():
    pol2_found = False
    for key2, pol2 in reversed(list(consolidated_polilies_p1.items())):    # to speed up the search by reversed the list
        if pol1['set dstaddr'] == pol2['set dstaddr'] and pol1['set srcaddr'] == pol2['set srcaddr'] and pol1['set dstintf'] == pol2['set dstintf'] and pol1['set srcintf'] == pol2['set srcintf']:
            pol2_found = True
            # print('consolidate policy:{} to policy:{}'.format(key1, key2))
            pol2['set service'][0] = pol2['set service'][0] + ' ' + pol1['set service'][0]
            break
    if not pol2_found:
        # print('adding new policy:{}'.format(key1))
        consolidated_polilies_p1[key1] = pol1

print('phase2 consolidation by combining dstaddr')
consolidated_polilies_p2 = defaultdict(f)
for key1, pol1 in consolidated_polilies_p1.items():
    pol2_found = False
    for key2, pol2 in reversed(list(consolidated_polilies_p2.items())):    # to speed up the search by reversed the list
        if pol1['set service'] == pol2['set service'] and pol1['set srcaddr'] == pol2['set srcaddr'] and pol1['set dstintf'] == pol2['set dstintf'] and pol1['set srcintf'] == pol2['set srcintf']:
            pol2_found = True
            # print('consolidate policy:{} to policy:{}'.format(key1, key2))
            pol2['set dstaddr'][0] = pol2['set dstaddr'][0] + ' ' + pol1['set dstaddr'][0]
            break
    if not pol2_found:
        # print('adding new policy:{}'.format(key1))
        consolidated_polilies_p2[key1] = pol1

print('phase3 consolidation by combining srcaddr')
consolidated_polilies_p3 = defaultdict(f)
for key1, pol1 in consolidated_polilies_p2.items():
    pol2_found = False
    for key2, pol2 in reversed(list(consolidated_polilies_p3.items())):    # to speed up the search by reversed the list
        if pol1['set service'] == pol2['set service'] and pol1['set dstaddr'] == pol2['set dstaddr'] and pol1['set dstintf'] == pol2['set dstintf'] and pol1['set srcintf'] == pol2['set srcintf']:
            pol2_found = True
            # print('consolidate policy:{} to policy:{}'.format(key1, key2))
            pol2['set srcaddr'][0] = pol2['set srcaddr'][0] + ' ' + pol1['set srcaddr'][0]
            break
    if not pol2_found:
        # print('adding new policy:{}'.format(key1))
        consolidated_polilies_p3[key1] = pol1

# niceprint(consolidated_polilies_p3)
print('before consolidateion there are {} policies, phase1 consolidate services down to {} policies, phase2 consolidate dstaddr down to {} policyes, phase3 consolidate srcaddr down to {} policyes'.format(len(config['config vdom']['edit "root"']['config firewall policy']), len(consolidated_polilies_p1), len(consolidated_polilies_p2), len(consolidated_polilies_p3)))

sum = 0
for key1, pol1 in consolidated_polilies_p3.items():
    sum = sum + len(pol1['set service'][0].split(' ')) * len(pol1['set srcaddr'][0].split(' ')) * len(pol1['set dstaddr'][0].split(' '))
print('convert back to {} original policies'.format(sum))