"""Native JSONC parsing shared by server-side resource import."""
import json
from app.management import fail

def jsonc(text):
    out, i, quoted, escape = [], 0, False, False
    while i < len(text):
        char = text[i]
        if quoted:
            out.append(char)
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                quoted = False
            i += 1
        elif char == '"':
            quoted = True
            out.append(char)
            i += 1
        elif text[i:i+2] == '//':
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
        elif text[i:i+2] == '/*':
            end = text.find('*/', i + 2)
            if end < 0:
                fail('Unterminated JSONC comment')
            out.append(' ')
            i = end + 2
        else:
            out.append(char)
            i += 1
    # Remove trailing commas outside JSON strings.
    text, out, quoted, escape = ''.join(out), [], False, False
    for i, char in enumerate(text):
        if not quoted and char == ',' and text[i+1:].lstrip().startswith(('}', ']')):
            continue
        out.append(char)
        if quoted:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
    try:
        value = json.loads(''.join(out).lstrip('\ufeff'))
        if not isinstance(value, dict):
            fail('OpenCode config must be an object')
        return value
    except ValueError:
        fail('Invalid JSON/JSONC configuration')

