#!/usr/bin/env python3
"""
lift-to-covenant-floor.py — port the trunk's covenant mechanism to a surface.

The trunk (confluence-TRUNK.html) holds the 18px floor ONE way:
    html { font-size: 18px }   + 446 rem-based declarations, 391 of them 1rem.
The floor lives at the root. Hierarchy is carried by weight/colour/space,
not by shrinking text below the floor.

This script ports that mechanism to a surface that hard-codes px:
  1. root  -> html { font-size: 18px }
  2. font-size:Npx        -> max(1, N/18) rem
  3. font-size:<1rem      -> 1rem
  4. font-size:clamp(...) -> px args to rem, minimum floored at 1rem
Sizes at or above the floor keep their rendered size exactly.
Sizes below it rise to the floor. Nothing shrinks.
"""
import re, sys

ROOT_PX = 18.0

def to_rem(px, floor=True):
    r = px / ROOT_PX
    if floor and r < 1: r = 1.0
    return ('%.3f' % r).rstrip('0').rstrip('.') + 'rem'

def lift(src):
    log = []
    s = src

    # 2. clamp() first (so bare-px rule cannot touch its args)
    def fix_clamp(m):
        args = m.group(1)
        parts = [a.strip() for a in args.split(',')]
        out = []
        for i, a in enumerate(parts):
            pm = re.fullmatch(r'([0-9.]+)px', a)
            if pm:
                out.append(to_rem(float(pm.group(1)), floor=(i == 0)))
            else:
                out.append(a)
        log.append('clamp(%s) -> clamp(%s)' % (args, ','.join(out)))
        return 'font-size:clamp(%s)' % ','.join(out)
    s = re.sub(r'font-size:\s*clamp\(([^)]*)\)', fix_clamp, s)

    # 3. bare px
    def fix_px(m):
        px = float(m.group(1))
        r = to_rem(px)
        log.append('%gpx -> %s%s' % (px, r, '   [LIFTED]' if px < ROOT_PX else ''))
        return 'font-size:' + r
    s = re.sub(r'font-size:\s*([0-9.]+)px', fix_px, s)

    # 4. sub-1rem
    def fix_rem(m):
        v = float(m.group(1))
        if v < 1:
            log.append('%grem -> 1rem   [LIFTED]' % v)
            return 'font-size:1rem'
        return m.group(0)
    s = re.sub(r'font-size:\s*(0?\.[0-9]+)rem', fix_rem, s)

    # LAST: the root. Done after the px pass, because an 18px root written first
    # is itself a "font-size:18px" declaration and the px pass rewrites it to
    # 1rem — a self-referential root that silently falls back to 16px and puts
    # every size below the floor. Order is load-bearing here.
    before = s
    s = re.sub(r'(html\s*\{[^}]*?)font-size:\s*(?:100%|1rem)', r'\g<1>font-size:18px', s, count=1)
    if s != before:
        log.append('root: -> font-size:18px  [set last]')
    else:
        s2 = re.sub(r'(html\s*\{)', r'\g<1>font-size:18px;', s, count=1)
        if s2 != s:
            s = s2; log.append('root: inserted font-size:18px  [set last]')

    return s, log

if __name__ == '__main__':
    src = open(sys.argv[1], encoding='utf-8').read()
    out, log = lift(src)
    open(sys.argv[2], 'w', encoding='utf-8').write(out)
    for l in log: print('   ', l)
    print('   %d changes' % len(log))
