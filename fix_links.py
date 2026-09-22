import os

ROUTES = {
    'landing':           '/',
    'student_login':     '/student_login',
    'enroll':            '/enroll',
    'waiting':           '/waiting',
    'exam':              '/exam',
    'submitted':         '/submitted',
    'invigilator_login': '/invigilator_login',
    'invigilator':       '/invigilator',
}

def fix(content):
    for name, route in ROUTES.items():
        # Match every prefix variant the templates and JS use:
        #   "x.html"   '/templates/x.html'   '../templates/x.html'
        # in single, double, and backtick quotes.
        for prefix in ('', '/templates/', '../templates/'):
            for q in ('"', "'", '`'):
                content = content.replace(
                    f'{q}{prefix}{name}.html',
                    f'{q}{route}'
                )
    return content

changed_files = []
for folder in ('templates', 'static/js'):
    for f in os.listdir(folder):
        if not (f.endswith('.html') or f.endswith('.js')):
            continue
        path = os.path.join(folder, f)
        s = open(path, encoding='utf-8').read()
        n = fix(s)
        if s != n:
            open(path, 'w', encoding='utf-8').write(n)
            changed_files.append(path)
            print(f'patched: {path}')
        else:
            print(f'no change: {path}')

print(f'\n{len(changed_files)} file(s) updated.')