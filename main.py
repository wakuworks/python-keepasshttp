# -*- coding: utf-8 -*-

import time
import getpass
import os.path
import sys
import base64
import json
import socket
from kptool.keepassdb import keepassdb
import keepass_crypt
import optparse
import ConfigParser

DEFAULT_CONFIG_PATH = '/etc/keepasshttp.conf'

config_path = DEFAULT_CONFIG_PATH
db_path     = None
password    = None

parser = optparse.OptionParser(usage='%prog [options] [db_path]')
parser.add_option('-c',
                  '--config-file',
                  dest='config_path',
                  help='config file path')
parser.add_option('-p',
                  '--password',
                  dest='password',
                  help='kdb password')

(options, args) = parser.parse_args()

if not options.config_path is None:
  config_path = options.config_path

if os.path.exists(config_path):
  conf = ConfigParser.SafeConfigParser()
  conf.read(config_path)
  
  if conf.has_option('keepass', 'db_path'):
    db_path = conf.get('keepass', 'db_path');
  
  if conf.has_option('keepass', 'password'):
    password = conf.get('keepass', 'password')

elif not options.config_path is None:
  print 'config file does not exist.'
  sys.exit()

if db_path is None:
  if len(args) == 1 and os.path.exists(args[0]):
    db_path = args[0]
  else:
    parser.print_help()
    sys.exit()

print "KeePass DB v1 path:" + db_path

if password is None:
  if not options.password is None:
    password = options.password
  else:
    password = getpass.getpass('Enter Password: ')

def test_associate(response):
    response['Id'] = 'chromeipass'
    response['Success'] = False

    keyfile = json.loads(open('keyfile.txt').read())
    key = base64.b64decode(keyfile['Key']);
    iv  = base64.b64decode(response['Nonce'])
    verifier = base64.b64decode(response['Verifier'])

    kpc = keepass_crypt.KeePassCrypt(key, iv)

    if base64.b64encode(iv) == kpc.decrypt(verifier):
        response['Success'] = True

    return response

def get_logins(response):
    global db_path
    global password

    response['Id'] = 'chromeipass'
    response['Success'] = True

    keyfile = json.loads(open('keyfile.txt').read())
    key = base64.b64decode(keyfile['Key']);
    iv = base64.b64decode(response['Nonce'])

    kpc = keepass_crypt.KeePassCrypt(key, iv)
    url = kpc.decrypt(base64.b64decode(response['Url']))

    k = keepassdb.KeepassDBv1(db_path, password)
    response['Entries'] = []
    for e in k.find_entries(url):
        entry = {}
        entry['Name']     = base64.b64encode(kpc.encrypt(e['title']))
        entry['Login']    = base64.b64encode(kpc.encrypt(e['username']))
        entry['Uuid']     = base64.b64encode(kpc.encrypt(e['id']))
        entry['Password'] = base64.b64encode(kpc.encrypt(e['password']))
        response['Entries'].append(entry)

    return response

def handle_request(request):

  #print '-- start handle_request ------'
  #print request
  #print '-- close handle_request ------'

  header, body = request.split('\r\n\r\n')
  response = json.loads(body)

  if response['RequestType'] == 'associate':
    response['Id'] = 'chromeipass'
    response['Success'] = False

    key = base64.b64decode(response['Key'])
    iv  = base64.b64decode(response['Nonce'])
    verifier = base64.b64decode(response['Verifier'])

    kpc = keepass_crypt.KeePassCrypt(key, iv)

    if base64.b64encode(iv) == kpc.decrypt(verifier):
      response['Success'] = True

      file_handle = open('keyfile.txt', 'w')
      file_handle.write(body)
      file_handle.close()

  elif response['RequestType'] == 'test-associate':
      response = test_associate(response)

  elif response['RequestType'] == 'get-logins':
      response = get_logins(response)

  else:
    print '-- start unknown request type response ------'
    print response

  http_response = create_response(json.dumps(response))
  return http_response

def create_response(body):
    data = []
    data.append('HTTP/1.1 200 OK')
    data.append('Date: ' + time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime()))
    data.append('Server: python-keypass-http')
    data.append('Connection: close')
    data.append('Content-Type: application/json; charset=utf-8')
    data.append('')
    data.append(body)
    data.append('')

    response = "\n".join(data)

    return response

class Server:
    def __init__(self):
        self.host = 'localhost'
        self.port = 19455

    def activate(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))

        while True:
            #print '-- begin while ------'
            server_sock.listen(3)

            #print 'Waiting for connections...'
            client_sock, client_address = server_sock.accept()
            receive_message = client_sock.recv(4096)

            if receive_message.rstrip() == "":
                sys.exit()

            response = handle_request(receive_message)

            client_sock.sendall(response)
            client_sock.close()

        server_sock.close()

server = Server()
server.activate()

