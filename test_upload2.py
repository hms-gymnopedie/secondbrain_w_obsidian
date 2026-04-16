import requests

with open('test.txt', 'w') as f:
    f.write('Test content'*10)

url = 'http://127.0.0.1:8000/api/upload'
files = [('files', ('test.txt', open('test.txt', 'rb'), 'text/plain'))]
data = {'folder': 'myfolder'}

r = requests.post(url, files=files, data=data)
print(r.status_code, r.text)
