"""PR3 Task 5 step 3: curl GET /api/scenarios/1/overview?month=14"""
import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:38089/api/scenarios/1/overview?month=14',
    method='GET',
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print('Status:', resp.status)
    print('Fields:', sorted(data.keys()))
    print()
    print('Overview month=14:')
    for k in sorted(data.keys()):
        v = data[k]
        print('  ' + k + ': $' + v)
