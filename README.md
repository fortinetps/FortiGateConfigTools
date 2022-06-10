# FortiGateConfigTools


##### Author :
Don Yao


#### Description : 
FortiGate Configuration Tools which use [pyfgtconflib](https://github.com/fortinetps/pyfgtconflib)


##### Install :


#### Usage :
[FGTPolicyConsolidate.py](https://github.com/fortinetps/FortiGateConfigTools/src/FGTPolicyConsolidate.py) script
Which takes FortiGate Configuration and consolidates firewall policies.
The consolidation processes have 3 steps, 
in step 1 it compares and consolidates services,
in step 2 it comapres and consolidates dstaddr,
in step 3 it compares and consolidates srcaddr.