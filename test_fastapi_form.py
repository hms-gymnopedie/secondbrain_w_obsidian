import requests

url = 'http://127.0.0.1:8001/api/upload'
files = [('files', ('test.txt', b'test short to write_note', 'text/plain'))]
data = {'folder': 'TestFolderWithShortDoc'}

try:
    r = requests.post(url, files=files, data=data)
    print("STATUS", r.status_code)
    print("TEXT", r.text)
except Exception as e:
    print(e)
