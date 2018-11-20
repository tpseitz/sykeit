#!/usr/bin/env python3
# Encoding: UTF-8
import json, sys, os
import database, objects, hypertext, web
CONFIG_FILES = ['~/.config/computer_manager.json',
  '/etc/computer_manager.json',
  os.path.split(os.path.realpath(__file__))[0] + '/computer_manager.json']

LANG = 'en'
AVAILABLE_LANGUAGES = { 'en', 'fi' }
_SHIFTS = {}

lang = {}

log = web.log
database.log = log
objects.log = log
hypertext.log = log

def init():
  global CONFIG_FILES, LANG, _SHIFTS, lang

  if 'CONFIG_FILE' in os.environ:
    CONFIG_FILES = [os.environ['CONFIG_FILE']] + CONFIG_FILES

  conf = {}
  for ffn in CONFIG_FILES:
    if os.path.exists(os.path.expanduser(ffn)):
      with open(ffn, 'r') as f: conf = json.loads(f.read())
      break
  if not conf: raise Exception('No config file')

  objects.SHIFT_NAMES = conf.get('shift_names', objects.SHIFT_NAMES)
  objects.DIRECTORY = conf.get('data_directory', objects.DIRECTORY)
  LANG = web.GET.get('lang') or web.COOKIES.get('lang') \
    or web.SESSION or conf.get('lang') or LANG
  hypertext.LAYOUT_DIRECTORY = conf.get('layout_directory', objects.DIRECTORY)
  web.SESSION_DIRECTORY = conf.get('session_directory', web.SESSION_DIRECTORY)

  database.configuration(conf)

  objects.SHIFTS = len(objects.SHIFT_NAMES)
  _SHIFTS = { objects.strip(nm): (i+1, nm)
    for i, nm in enumerate(objects.SHIFT_NAMES) }

  objects.DIRECTORY = os.path.expanduser(objects.DIRECTORY)
  hypertext.LAYOUT_DIRECTORY = os.path.expanduser(hypertext.LAYOUT_DIRECTORY)

  if LANG not in AVAILABLE_LANGUAGES: raise Exception('Unknown language')

  fdn = os.path.split(os.path.realpath(__file__))[0]
  ffn = os.path.join(fdn, 'lang-%s.json' % LANG)
  with open(ffn, 'r') as f: lang = json.loads(f.read())
  ffn = os.path.join(fdn, 'forms.json')
  with open(ffn, 'r') as f: hypertext.FORMS = json.loads(f.read())

  objects.lang = lang
  hypertext.lang = lang

  hypertext.GLOBALS['lang'] = lang
  hypertext.GLOBALS['script'] = os.environ.get('SCRIPT_NAME', '')

  hypertext.FUNCTIONS['menu'] = menu

  objects.loadData()

  hypertext.GLOBALS['list_days'] = enumerate(lang['WORKDAYS'])
  hypertext.GLOBALS['list_shifts'] \
    = [(i+1, d) for i, d in enumerate(objects.SHIFT_NAMES)]
  hypertext.GLOBALS['list_rooms'] \
    = [(i, r['name']) for i, r in enumerate(objects.ROOMS)]

  if 'lang' in web.GET: web.COOKIES['lang'] = web.GET['lang']

def runCommand(cmd, *argv):
  argv = list(argv)
  if cmd == 'list':
    if not argv:
      cls = sorted(objects.Computer._COMPUTERS.values(), key=lambda c: c.cid)
      for cpu in cls:
        print('%s' % (cpu,))
        for usr in sorted(cpu.users, key=lambda u: u.shift):
          print('  %s' % (usr,))
    elif argv[0] in ('computers', 'computer', 'comp', 'cpu', 'c'):
      cls = sorted(objects.Computer._COMPUTERS.values(), key=lambda c: c.cid)
      for cpu in cls:
        print('%s' % (cpu,))
    elif argv[0] in ('users', 'user', 'usr', 'u'):
      for usr in sorted(objects.User._USERS.values(), key=lambda u: u.uid):
        print('%s' % (usr,))
    else:
      log(0, lang['ERR_UNKNOWN_LIST'] % argv[0])
  elif cmd == 'add':
    if not argv:
      print('You must give type')
      return
    tp = argv.pop(0)
    if   tp in ('computer', 'comp', 'cpu', 'c'):
      for cpu in argv:
        print('Adding computer %s' % cpu)
        objects.Computer(cpu)
    elif tp in ('user', 'usr', 'u'):
      for usr in argv:
        print('Adding user %s' % usr)
        objects.User(usr)
    else:
      print('Unknown type: %s' % tp)
    objects.saveData()
  elif cmd in ('delete', 'del', 'remove'):
    for nm in argv: objects.delete(nm)
    objects.saveData()
  elif cmd == 'shift':
    if len(argv) < 3:
      print('Not enough parameters')
      return
    addShift(argv[0], argv[1], argv[2:])

  elif cmd == 'seat':
    if len(argv) == 2: usr, cpu = argv
    elif len(argv) == 1: usr, cpu = argv[0], None

    usr = REGEX_STRIP.sub('', usr.lower())
    if usr in objects.User._USERS:
      usr = objects.User._USERS[usr]
      print('Adding seat %s for user %s' % (cpu, usr))
      usr.assignComputer(cpu)
      objects.saveData()
    else:
      print('Unknown user')
  else:
    print('Unknown command: %s' % cmd)

def main():
  init()

  if len(sys.argv) < 2: runCommand('list')
  else: runCommand(*sys.argv[1:])

def computersVacant(shift):
  ls = []
  for cpu in objects.Computer._COMPUTERS.values():
    sls = { usr.shift for usr in cpu.users }
    if shift not in sls: ls.append(cpu)
  return sorted(ls, key=lambda c: c.cid)

def formData(data):
  name = data.get('_form', '')
  if name == 'adduser':
    u = objects.User(data['name'], int(data['shift']),
      map(int, data.get('days', '')))
    if u in objects.User._USERS.values():
      log(2, lang['MSG_ADD_USER'] % (str(u),))
      objects.saveData()
    web.redirect('users', 3)
  elif name == 'updateuser':
    u = objects.User._USERS[data['uid']]
    rc = u.assignShift(int(data['shift']), map(int, data['days']))
    objects.saveData()
    web.redirect('user/%s' % data['uid'], 3)
  elif name == 'addcomputer':
    c = objects.Computer(data['name'])
    if c in objects.Computer._COMPUTERS.values():
      log(2, lang['MSG_ADD_COMPUTER'] % (str(c),))
      objects.saveData()
    web.redirect('computers', 3)
  elif name == 'login':
    web.SESSION.update(database.checkPassword(data['username'], data['password']))
    if web.SESSION.get('username'):
      writeSession()
      web.redirect(data.get('source') or data['_next'], 3)
    else: web.redirect('login/failed', 5)
  else: log(0, 'Unknown form: %s' % (name,))

  web.redirect(data.get('_next', ''), 3)

def printDebugData():
  html = ''
  for key in sorted(os.environ):
    html += "%s = %r<br>\n" % (key, os.environ[key])
  html += '<hr>\n'
  for t in web.GET.items(): html += "%s = %r<br>\n" % t
  html += '<hr>\n'
  for t in web.COOKIES.items(): html += "%s = %r<br>\n" % t
  web.outputPage(html)

def menu():
  menu = { 'elements': [
    { 'title': '{{lang.COMPUTERS}}', 'path': 'computers' },
    { 'title': '{{lang.USERS}}', 'path': 'users' }]}
  for nm in objects.SHIFT_NAMES: menu['elements'].append({
    'title': nm, 'path': 'computers/' + nm })
  return hypertext.mustache('menu', menu)

def mainCGI():
  global HTTP, _SHIFTS

  path = web.startCGI(init)
  if len(path) == 0: path = ['computers']
  usr_lvl = web.SESSION.get('level', -1)

  if path[0] == 'debug' and usr_lvl >= 200: printDebugData()

  hypertext.GLOBALS['session'] = web.SESSION

  if usr_lvl >= 50:
    if path[0] == 'user' and len(path) == 2 and path[1] in objects.User._USERS:
      web.outputPage(hypertext.frame('user',
        { 'user': objects.User._USERS[path[1]].toDict() }))
    elif path[0] == 'computers':
      cls, shift = [], 0
      if len(path) > 1:
        sid = objects.strip(path[1])
        if sid in _SHIFTS: shift = _SHIFTS[sid][0]
      shfs = { i+1: { 'shift_name': n, 'presence': 5 * [True],
        'status': 'free', 'name': '{{lang.VACANT}}' }
          for i, n in enumerate(objects.SHIFT_NAMES) }
      for cpu in map(objects.Computer.toDict,
        objects.Computer._COMPUTERS.values()):
          uls = shfs.copy()
          for u in objects.User._USERS.values():
            if u.computer is None or u.computer.cid != cpu['cid']: continue
            uls[u.shift] = u.toDict()
          if shift > 0:
            cpu['user'] = uls.get(shift)
            cpu['users'] = []
          else:
            cpu['user'] =  uls.pop(1)
            cpu['users'] = [uls[i] for i in range(2, objects.SHIFTS+1)]
          cls.append(cpu)
      cls = sorted(cls, key=lambda c: c['name'])
      data = { 'shift_count': shift and 1 or objects.SHIFTS,
        'computers': cls }
      web.outputPage(hypertext.frame('computers', data))
    elif path[0] == 'users':
      uls = sorted(objects.User._USERS.values(), key=lambda u: u.name.lower())
      data = { 'users': [usr.toDict() for usr in uls] }
      web.outputPage(hypertext.frame('users', data))

  if usr_lvl >= 100:
    if path[0] == 'assign':
      if len(path) == 3 \
        and path[1] in objects.User._USERS \
        and path[2] in objects.Computer._COMPUTERS:
          objects.User._USERS[path[1]].assignComputer(path[2])
          objects.saveData()
          log(2, lang['MSG_ASSIGN_COMPUTER'] % (
            objects.Computer._COMPUTERS[path[2]].name,
            objects.User._USERS[path[1]].name))
          web.redirect('user/%s' % (path[1],), 3)
      elif len(path) == 2 and path[1] in objects.User._USERS:
        usr = objects.User._USERS[path[1]]
        dt = { 'user': usr.toDict(), 'computers':
          [{ 'id': cpu.cid, 'name': cpu.name }
            for cpu in computersVacant(usr.shift)] }
        web.outputPage(hypertext.frame(hypertext.mustache(
          hypertext.layout('assign'), dt)))
      else: log(0, lang['ERR_GERERIC']) #XXX
    elif path[0] == 'delete' and len(path) == 2:
      if path[1] in objects.User._USERS: rd = 'users'
      elif path[1] in objects.Computer._COMPUTERS: rd ='computers'
      else: rd = ''
      nm = objects.delete(path[1])
      if nm:
        objects.saveData()
        web.redirect(rd, 3, lang['MSG_DEL'] % (nm,))
      else:
        log(0, lang['ERR_UNKNOWN_UNIT'] % path[1])
    elif path[0] == 'form':
      handleForm()

  web.outputPage(hypertext.frame(hypertext.form('login', target='login')))

if __name__ == '__main__':
  if 'QUERY_STRING' in os.environ: mainCGI()
  else: main()

