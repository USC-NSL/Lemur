import json

data = {}  
data['nic'] = []  
data['nic'].append({  
    'name': 'intel_nic1',
    'ip': '204.57.7.12',
    'throughput': '40000',
    'core': '16',
    'pci': '5e:00.0',
    'driver': 'igb_uio'
})
'''
data['nic'].append({  
    'name': 'intel_nic2',
    'ip': '204.57.7.12',
    'throughput': '40000',
    'core': '8',
    'pci': 'af:00.0',
    'driver': 'igb_uio'
})
data['nic'].append({  
    'name': 'netronome',
    'ip': '204.57.7.41',
    'throughput': '40000',
    'core': '8',
    'pci': '5e:00.0',
    'driver': 'igb_uio'
})
'''
with open('device.txt', 'w') as outfile:  
    json.dump(data, outfile)
