"""Lossless argv proposal for an explicit PowerShell EncodedCommand transport.

Pure construction only: no subprocess, VM, shell or CAD is launched here.
"""

import base64
import json
from pathlib import PureWindowsPath

BOOTSTRAP = ('import base64,json,subprocess,sys;'
             'argv=json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"));'
             'p=subprocess.Popen(argv);sys.exit(p.wait())')


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def encoded_recipe_command(python_executable, argv):
    """Pass one JSON/base64 argv envelope; do not JSON-escape individual paths.

    Decoding and shell=False child launch happen in a Windows Python process.
    Does not repair already-corrupted argv, configure clients or retry a job.
    """
    if (not isinstance(python_executable, str) or '\0' in python_executable
            or not PureWindowsPath(python_executable).is_absolute()):
        raise ValueError('Use an explicit absolute Windows Python executable')
    if (not isinstance(argv, list) or not argv or not argv[0]
            or any(not isinstance(a, str) or '\0' in a for a in argv)):
        raise ValueError('Use a nonempty string argv without NUL characters')
    payload = base64.b64encode(json.dumps(argv, ensure_ascii=False).encode('utf-8')).decode('ascii')
    script = (f'& {_literal(python_executable)} {_literal("-c")} '
              f'{_literal(BOOTSTRAP)} {_literal(payload)}; exit $LASTEXITCODE')
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return {'powershell_argv': ['powershell.exe', '-NoProfile', '-NonInteractive',
                               '-EncodedCommand', encoded],
            'script': script, 'payload': payload, 'automatic_retry': False}
