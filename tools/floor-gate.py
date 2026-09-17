#!/usr/bin/env python3
"""
floor-gate.py — assert nothing on a surface renders below the 18px covenant floor.

Does NOT assume the root is 18px. Resolves it from the document and fails if it
is missing, self-referential, or a percentage. Exit 1 means it does not ship.
"""
import re, sys

FLOOR = 18.0

def gate(path):
    s = open(path, encoding='utf-8').read()
    halts, notes = [], []

    roots = re.findall(r'html\s*\{([^}]*)\}', s)
    root_px = None
    for body in roots:
        m = re.search(r'font-size:\s*([0-9.]+)(px|rem|em|%)', body)
        if m:
            v, u = float(m.group(1)), m.group(2)
            if u == 'px':
                root_px = v
            else:
                halts.append(f'root font-size is {m.group(1)}{u} — not an absolute px floor '
                             f'({"self-referential" if u in ("rem","em") else "inherits browser default"})')
            break
    if root_px is None and not halts:
        halts.append('no root font-size on html — floor is unenforced')
    if root_px is not None:
        if root_px < FLOOR:
            halts.append(f'root font-size {root_px}px is below the {FLOOR:.0f}px floor')
        notes.append(f'root = {root_px:g}px')

    base = root_px or 16.0

    for m in re.finditer(r'font-size:\s*([0-9.]+)px', s):
        if float(m.group(1)) < FLOOR:
            halts.append(f'hard px font-size {m.group(1)}px')
    for m in re.finditer(r'font-size:\s*([0-9.]*\.?[0-9]+)rem', s):
        r = float(m.group(1))
        if r * base < FLOOR:
            halts.append(f'{m.group(1)}rem renders at {r*base:.1f}px')
    for m in re.finditer(r'font-size:\s*clamp\(([^)]*)\)', s):
        first = m.group(1).split(',')[0].strip()
        mm = re.fullmatch(r'([0-9.]+)(px|rem)', first)
        if mm:
            v = float(mm.group(1))
            rendered = v if mm.group(2) == 'px' else v * base
            if rendered < FLOOR:
                halts.append(f'clamp minimum {first} renders at {rendered:.1f}px')

    return halts, notes

if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        halts, notes = gate(p)
        tag = 'PASS' if not halts else 'HALT'
        print(f'{tag}  {p}   {" · ".join(notes)}')
        for h in halts:
            print(f'        {h}')
        if halts: bad = 1
    sys.exit(bad)
