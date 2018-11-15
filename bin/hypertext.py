# Encoding: UTF-8
import json, re, os
LAYOUT_DIRECTORY = '~/layout'
SHIFT_NAMES, FORMS, FUNCTIONS, GLOBALS = [], {}, {}, {}

HTML_CELL_FREE = None
HTML_CELL_RESERVED = None

REGEX_FORM_VARIABLE = re.compile(r'{[a-z_]+}')
REGEX_MUSTACHE_BLOCK = re.compile(r'\{\{\#(\$\d+|[A-Za-z_\.]+)(=[A-Za-z\d\._]+)?\}\}')
REGEX_MUSTACHE_VARIABLE = re.compile(
  r'\{\{(\&?)(\$\d+|[A-Za-z\._]+)(\:[A-Za-z\d_,]+)?\}\}')
REGEX_MUSTACHE_BLOCK_BARE = re.compile(r'\{\{[^\{\}]+\}\}')

def log(lvl, msg): pass

def link(path, text):
  if path and path[0] == '/': path = path[1:]
  return '<a href="%s/%s">%s</a>' % (GLOBALS['script'], path, text)

def form(name, data={}, formdata=None, redirect=None):
  if name in FORMS: formdata = FORMS[name]
  elif formdata is None: return 'form(%s)' % (name,)
  title, button, redirect = formdata.pop(0)
  if not title: title = name

  html = '<form id="%s" action="{{script}}/form"' % (name,) \
    + ' method="post" enctype="multipart/form-data">\n'
  html += '  <p>%s</p>' % (title,)
  html += '  <input type="hidden" name="_form" value="%s"><br>\n' % (name,)

  for iid, tp, nm, vls in formdata:
    if isinstance(vls, str) and REGEX_FORM_VARIABLE.match(vls):
      vls = GLOBALS[vls[1:-1]]

    if   tp == 'static':
      html += '  %s: %s<br>\n' % (nm, vls[1])
      html += '  <input type="hidden" name="%s" value="%s"><br>\n' \
        % (iid, vls[0])
    elif tp == 'text':
      html += '  %s\n' % (nm,)
      html += '  <input type="text" name="%s" value=""><br>\n' % (iid,)
    elif tp in ('select', 'select0'):
      iter(vls) # Test that vls is of iterable type
      html += '  %s\n' % (nm,)
      html += '  <select name="%s" required="true">\n' % iid
      if tp == 'select0': html += '    <option value="null">-</option>\n'
      for i, n in vls:
        html += '    <option value="%s">%s</option>\n' % (i, n)
      html += '  </select><br>\n'
    elif tp == 'checklist':
      html += '  <strong>%s:</strong>\n' % (nm,)
      for i, n in vls:
        html += '  <input type="checkbox" name="%s" value="%s">%s\n' \
          % (iid, i, n)
      html += '  <br>\n'
    elif tp == 'password':
      html += '  %s\n' % (nm,)
      html += '  <input type="password" name="%s" value=""><br>\n' % (iid,)

  html += '  <input type="hidden" name="_next" value="%s"><br>\n' % (redirect,)
  html += '  <input id="send" class="button" type="submit" value="%s"><br>\n' \
    % (button,)
  html += '</form>\n'

  return html

FUNCTIONS['form'] = form

def layout(name):
  ffn = os.path.join(os.path.expanduser(LAYOUT_DIRECTORY), '%s.html' % (name,))
  if not os.path.isfile(ffn): return name
  with open(ffn, 'r') as f: html = f.read()
  return html

REGEX_LAYOUT_NAME = re.compile(r'^[a-z\d_]+$')
def frame(html, data={}):
  if REGEX_LAYOUT_NAME.match(html): html = layout(html)
  start, end = layout('frame').split('{{content}}')
  return mustache(start + html + end, data)

MAX_ITERATIONS, MAX_PAGE_SIZE = 15, 1048576
MAX_BLOCK_LOOPS, MAX_VARIABLE_LOOPS = 10, 150
_BASE_DATA = {}
def mustache(html, data={}, default=None, *outside):
  global _BASE_DATA, GLOBALS

  # Check for max iterations
  if len(outside) > MAX_ITERATIONS: log(0, 'Stack overflow')
  # Check for too larde html page
  if len(html) > MAX_PAGE_SIZE: log(0, 'Page is too large')

  if REGEX_LAYOUT_NAME.match(html): html = layout(html)

  if not _BASE_DATA:
    _BASE_DATA = FUNCTIONS.copy()
    _BASE_DATA.update(GLOBALS)

  count = 0
  while count < MAX_BLOCK_LOOPS:
    count += 1
    mt = REGEX_MUSTACHE_BLOCK.search(html)
    if mt is None: break

    tag, key, comp = mt.group(0), mt.group(1), mt.group(2)
    val = data
    i, l = html.find('{{/%s}}' % key), 5 + len(key)
    if i < 0: log(0, 'Layout error: No end tag for %s' % (tag,))
    start, blk, nblk, end = html[:mt.start()], html[mt.end():i], '', html[i+l:]
    if '{{^%s}}' % key in blk: blk, nblk = blk.split('{{^%s}}' % key, 1)

    if key == '_': val = default
    else:
      for k in key.split('.'):
        for dt in (val,) + outside + (_BASE_DATA,):
          val = dt.get(k, '{{}}')
          if val != '{{}}': break
        if val ==  '{{}}':
          val = '[%s]' % key
          break

    if comp:
      cp = {}
      for k in comp[1:].split('.'):
        for dt in (cp,) + outside + (_BASE_DATA,):
          cp = dt.get(k, '{{}}')
          if cp != '{{}}': break
        if cp ==  '{{}}': break
      val = val == cp

    if not val:
      ht = mustache(nblk, data, *outside)
    elif isinstance(val, (tuple, list, set)):
      ht = ''
      for vv in val:
        dt = data
        if isinstance(vv, dict): dt = vv
        elif isinstance(vv, (tuple, list)):
          dt = { '$%d' % (i + 1): n for i, n in enumerate(vv)}
        ht += mustache(blk, dt, vv, data, *outside)
    else:
      dt = data
      if isinstance(val, dict): dt = val
      ht = mustache(blk, dt, val, data, *outside)
    html = start + ht + end

  count = 0
  while count < MAX_VARIABLE_LOOPS:
    count += 1
    mt = REGEX_MUSTACHE_VARIABLE.search(html)
    if mt is None: break

    tp, key, arg = mt.groups()
    tag, rep = mt.group(0), '[no data]'

    val = data
    if key == '_': val = default
    else:
      for k in key.split('.'):
        for dt in (val,) + outside + (_BASE_DATA,):
          val = dt.get(k, '{{}}')
          if val != '{{}}': break
        if val ==  '{{}}':
          val = '[%s]' % key
          break

    if callable(val):
      argv = tuple()
      if arg and arg[0] == ':': argv = arg[1:].split(',')
      rep = val(*argv)
    elif isinstance(val, (tuple, list, set)):
      rep = ', '.join(map(str, val))
    else:
      rep = str(val)

    html = html.replace(tag, rep)

  return html

