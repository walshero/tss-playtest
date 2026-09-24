#!/usr/bin/env python3
"""
STUDIO FINGERS — PLAY MODE. The hand that actually plays the game.

Studio Fingers (static) loads a page once and measures every control. It never
presses Start, so it has never seen level 1. Founder, 2026-09-24, on Flok:
"on phone I can't even see the whole post I'm reviewing." Every static gate passed
that build. The defect lives three taps in, so the gate has to go three taps in.

Play mode drives a game on a real touch viewport, the way a player would, and
checks what the player can see and do AT EACH MOMENT OF PLAY:

  HALTS (exit 1, do not ship)
  P-FOCUS      the thing the player is judging (the step's `focus`) is not fully
               visible: clipped by the screen or by a scrolling box it sits in.
               Measured as the fraction of its area that survives every clip.
  P-TOGETHER   the focus and the action are not on screen at the same time. If you
               have to scroll away from the post to press Boost, you are not
               watching what your thumb does, and the lesson happens off-screen.
  P-DEAD       the action changed nothing the player can see (no visible state
               change within 700ms).
  P-STUCK      the playthrough could not reach the end within its step budget.
  P-ERROR      the page threw a JavaScript error during play.

  NOTES (print, do not block)
  N-FOLD       how far the game screen runs past the bottom of the phone (px). A
               game screen that needs page scrolling is a document, not a scene.
  N-REACH      the action sits above the one-thumb arc (top 60% of the screen).
  N-PRIMARY    more than one filled, full-width primary control on one screen:
               two things shouting "press me" is a cohesion fault, not a floor.
  N-WANDER     (wander mode) where a naive player, pressing whatever looks most
               pressable, got stuck or detoured. Discoverability, not correctness.

Two ways to play:
  --hand FILE.json   a scripted playthrough (the designer's path). Deterministic.
  --wander           no script: at every screen, press the most prominent thing in
                     reach, and if nothing moves, try scrolling. The player who did
                     not read the brief.

Every run writes a FILMSTRIP (one frame per step, per viewport) so the founder can
see the playthrough without playing it: <outdir>/<viewport>/NN-label.png and a
contact sheet <outdir>/<viewport>-sheet.png.

Usage:
  python3 studio-fingers-play.py GAME.html --hand hands/the-console.hand.json [--out DIR]
  python3 studio-fingers-play.py GAME.html --wander [--out DIR]
  python3 studio-fingers-play.py --self-test
"""
import json, os, sys, time, hashlib

FOCUS_FLOOR = 0.98      # fraction of the focus that must be visible [HOUSE, measured]
THUMB_ARC = 0.40        # CITED: comfortable one-thumb reach = bottom 40% of the screen
DEAD_MS = 700           # a response slower than this reads as "nothing happened"
VIEWPORTS = [           # the two phones that bracket the classroom
    {"name": "small-phone-375x667", "width": 375, "height": 667},   # iPhone SE / 8
    {"name": "phone-393x852", "width": 393, "height": 852},         # iPhone 15
]

# ---- in-page measurement ---------------------------------------------------------
JS_VISIBLE = r"""
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return {found:false};
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return {found:true, area:0, ratio:0, rect:[0,0,0,0]};
  let L = r.left, T = r.top, R = r.right, B = r.bottom;
  // clip by every ancestor that clips its overflow
  for (let a = el.parentElement; a; a = a.parentElement) {
    const cs = getComputedStyle(a);
    if (/(hidden|auto|scroll|clip)/.test(cs.overflow + cs.overflowX + cs.overflowY)) {
      const ar = a.getBoundingClientRect();
      L = Math.max(L, ar.left); T = Math.max(T, ar.top);
      R = Math.min(R, ar.right); B = Math.min(B, ar.bottom);
    }
  }
  // clip by the screen
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  L = Math.max(L, 0); T = Math.max(T, 0); R = Math.min(R, vw); B = Math.min(B, vh);
  const vis = Math.max(0, R - L) * Math.max(0, B - T);
  const area = r.width * r.height;
  return {found:true, area, ratio: area ? vis/area : 0,
          rect:[Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)],
          vh, vw};
}
"""

JS_SCENE = r"""
() => {
  const de = document.documentElement;
  // fold = how much of the ACTIVE screen is below the glass right now (not the whole
  // document: studio chrome below a game is not the game).
  const on = document.querySelector('.screen.on,[id^="sc-"].on');
  const fold = on ? on.getBoundingClientRect().bottom - window.innerHeight
                  : de.scrollHeight - window.innerHeight;
  const out = {fold: Math.max(0, Math.round(fold)), primaries: []};
  const vh = window.innerHeight, vw = de.clientWidth;
  document.querySelectorAll('button,[role="button"],a[href]').forEach(el => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width < vw * 0.6 || r.height < 44) return;
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return;
    if (r.bottom <= 0 || r.top >= vh) return;
    const bg = cs.backgroundColor;
    const filled = bg && !/rgba\(.*,\s*0\)|transparent/.test(bg);
    if (filled) out.primaries.push((el.textContent||'').trim().replace(/\s+/g,' ').slice(0,30));
  });
  return out;
}
"""

JS_FINGERPRINT = r"""
(sel) => {
  // What the player can SEE of the play area: text + image sources + classes +
  // meter values, restricted to the given region (or the active screen).
  const root = (sel && document.querySelector(sel)) || document.body;
  const bits = [];
  root.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    if (el.children.length === 0) bits.push((el.textContent||'').trim());
    if (el.tagName === 'IMG') bits.push(el.src.slice(-40));
    if (el.getAttribute('aria-valuenow')) bits.push('v'+el.getAttribute('aria-valuenow'));
    if (el.style && el.style.width) bits.push('w'+el.style.width);
    if (el.scrollTop) bits.push('s'+Math.round(el.scrollTop/40));   // content moved under the thumb
    bits.push(el.className && el.className.baseVal === undefined ? el.className : '');
  });
  const on = document.querySelector('.screen.on,[data-screen].on,.on[id^="sc-"]');
  return (on ? on.id : '') + '#' + bits.join('|');
}
"""

JS_SALIENT = r"""
() => {
  // What a naive player presses: the most prominent control on screen.
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  const cands = [];
  document.querySelectorAll('button,[role="button"],a[href],[onclick]').forEach((el, i) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width < 24 || r.height < 24) return;
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return;
    if (el.disabled || el.closest('[hidden]')) return;
    if (el.getAttribute('aria-disabled') === 'true' || cs.pointerEvents === 'none') return;
    if (r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw) return;
    if (el.closest('header,nav,.se-rail,.se-bar,.se-chrome')) return;   // chrome is not the game
    if (el.tagName === 'A' && /^https?:/.test(el.getAttribute('href')||'')) return; // leaves the game
    const bg = cs.backgroundColor;
    const filled = bg && !/rgba\(.*,\s*0\)|transparent/.test(bg);
    const area = Math.min(r.width, vw) * r.height;
    const thumb = (r.top + r.height/2) > vh * (1 - 0.40) ? 1.3 : 1;
    const score = area * (filled ? 1.6 : 1) * thumb;
    el.setAttribute('data-sf-id', 'sf' + i);
    cands.push({id: 'sf' + i, score, label: (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,30)});
  });
  cands.sort((a, b) => b.score - a.score);
  return cands;
}
"""

JS_SCROLLER = r"""
() => {
  // the biggest thing on screen that scrolls on its own
  let best = null, bestA = 0;
  document.querySelectorAll('*').forEach((el, i) => {
    const cs = getComputedStyle(el);
    if (!/(auto|scroll)/.test(cs.overflowY)) return;
    if (el.scrollHeight <= el.clientHeight + 4) return;
    const r = el.getBoundingClientRect();
    const a = r.width * r.height;
    if (a > bestA) { bestA = a; best = el; el.setAttribute('data-sf-scroll', '1'); }
  });
  if (!best) return null;
  const r = best.getBoundingClientRect();
  return {x: r.left + r.width/2, y: r.top + r.height/2};
}
"""


def chromium_path():
    for p in ('/opt/pw-browsers/chromium', os.environ.get('CHROME_PATH', '')):
        if p and os.path.exists(p) and os.path.isfile(p):
            return p
    return None


def swipe_up(page, x, y, dist=320):
    """A real touch scroll gesture — how a thumb moves a feed."""
    # Real touch events, finger down / drag / lift. (Chromium's synthesizeScrollGesture
    # with gestureSourceType 'touch' is a no-op headless — measured 2026-09-24 on a plain
    # overflow box: 0px moved. A gate that swipes with a dead finger reports the GAME as
    # dead. The harness is the first suspect.)
    cdp = page.context.new_cdp_session(page)
    steps = 12
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
    for i in range(1, steps + 1):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove',
                 'touchPoints': [{'x': x, 'y': max(1, y - dist * i / steps)}]})
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    cdp.detach()


class Run:
    def __init__(self, out, vp):
        self.out, self.vp = out, vp
        self.halts, self.notes, self.frames = [], [], []
        self.n = 0
        self.trace = []
        os.makedirs(os.path.join(out, vp['name']), exist_ok=True)

    def frame(self, page, label):
        self.n += 1
        safe = ''.join(c if c.isalnum() else '-' for c in label)[:40]
        p = os.path.join(self.out, self.vp['name'], f'{self.n:02d}-{safe}.png')
        page.screenshot(path=p)
        self.frames.append((p, label))
        return p

    def halt(self, code, where, msg):
        self.halts.append((code, where, msg))

    def note(self, code, where, msg):
        self.notes.append((code, where, msg))


def measure_step(page, run, label, focus, action):
    """The heart of play mode: at this moment, can the player see what they judge,
    and touch what acts on it, at the same time?"""
    fv = page.evaluate(JS_VISIBLE, focus) if focus else None
    av = page.evaluate(JS_VISIBLE, action) if action else None
    if fv is not None:
        if not fv['found']:
            run.halt('P-FOCUS', label, f'focus {focus!r} not on the page')
        elif fv['ratio'] < FOCUS_FLOOR:
            run.halt('P-FOCUS', label, f'only {fv["ratio"]*100:.0f}% of the focus is visible '
                     f'({focus}, {fv["rect"][3]}px tall)')
    if fv and av and fv.get('found') and av.get('found'):
        if fv['ratio'] >= FOCUS_FLOOR and av['ratio'] < 0.9:
            run.halt('P-TOGETHER', label, f'focus visible but the action is {av["ratio"]*100:.0f}% on screen')
        elif fv['ratio'] < FOCUS_FLOOR and av['ratio'] >= 0.9:
            run.halt('P-TOGETHER', label, 'the action is in reach but what it acts on is not')
        ay = av['rect'][1] + av['rect'][3] / 2
        if ay < av['vh'] * (1 - THUMB_ARC):
            run.note('N-REACH', label, f'action centre at {ay/av["vh"]*100:.0f}% down the screen')
    sc = page.evaluate(JS_SCENE)
    if sc['fold'] > 8:
        run.note('N-FOLD', label, f'screen runs {sc["fold"]}px past the bottom of the phone')
    if len(sc['primaries']) > 1:
        run.note('N-PRIMARY', label, 'competing primaries: ' + ' | '.join(sc['primaries']))
    return fv, av


def act(page, step):
    """Perform one player action. Returns nothing; effects are measured by caller."""
    kind = step.get('do', 'tap')
    if kind == 'tap':
        page.tap(step['action'])
    elif kind == 'swipe':
        page.locator(step['action']).scroll_into_view_if_needed()
        box = page.locator(step['action']).bounding_box()
        swipe_up(page, box['x'] + box['width'] / 2, box['y'] + box['height'] * 0.7,
                 step.get('distance', 320))
    elif kind == 'wait':
        page.wait_for_timeout(step.get('ms', 500))
    elif kind == 'eval':
        page.evaluate(step['js'])


def play_hand(page, run, hand):
    region = hand.get('region')
    for si, step in enumerate(hand['steps']):
        label = step.get('label', f'step{si+1}')
        if step.get('wait_for'):
            try:
                page.wait_for_selector(step['wait_for'], state='visible', timeout=4000)
            except Exception:
                run.halt('P-STUCK', label, f'never reached {step["wait_for"]}')
                run.frame(page, label + '-STUCK')
                return False
        reps = step.get('repeat_until')
        tries = 0
        while True:
            focus, action = step.get('focus'), step.get('action')
            before = page.evaluate(JS_FINGERPRINT, region)
            measure_step(page, run, label, focus, action if step.get('do', 'tap') == 'tap' else None)
            if tries == 0:
                run.frame(page, label)
            try:
                act(page, step)
            except Exception as e:
                run.halt('P-STUCK', label, f'could not {step.get("do","tap")} {action!r}: {str(e).splitlines()[0][:90]}')
                run.frame(page, label + '-STUCK')
                return False
            page.wait_for_timeout(DEAD_MS)
            after = page.evaluate(JS_FINGERPRINT, region)
            if step.get('do', 'tap') != 'wait' and before == after and not step.get('may_be_still'):
                run.halt('P-DEAD', label, f'{step.get("do","tap")} on {action!r} changed nothing visible')
            tries += 1
            if not reps:
                break
            if page.locator(reps).count() and page.locator(reps).first.is_visible():
                measure_step(page, run, label + ' (after)', step.get('focus'), None)
                run.frame(page, label + '-done')
                break
            if tries >= step.get('max', 25):
                run.halt('P-STUCK', label, f'{tries} tries and {reps!r} never appeared')
                run.frame(page, label + '-STUCK')
                return False
    return True


def wander(page, run, budget=80, end_sel=None):
    """The player who did not read the brief."""
    seen_labels, stalls, last = [], 0, None
    for i in range(budget):
        if end_sel and page.locator(end_sel).count() and page.locator(end_sel).first.is_visible():
            run.frame(page, 'wander-end')
            return True
        cands = page.evaluate(JS_SALIENT)
        before = page.evaluate(JS_FINGERPRINT, None)
        pressed = None
        for c in cands:
            if seen_labels[-6:].count(c['label']) >= 4:   # stop hammering one control
                continue
            pressed = c
            break
        if pressed:
            try:
                page.tap(f'[data-sf-id="{pressed["id"]}"]', timeout=2000)
            except Exception:
                pressed = None
        if not pressed:
            pt = page.evaluate(JS_SCROLLER)
            if pt:
                swipe_up(page, pt['x'], pt['y'])
            else:
                page.mouse.wheel(0, 400)
        page.wait_for_timeout(DEAD_MS)
        after = page.evaluate(JS_FINGERPRINT, None)
        seen_labels.append(pressed['label'] if pressed else '(scroll)')
        run.trace.append(seen_labels[-1] + ('' if before != after else '  [no change]'))
        if before == after:
            stalls += 1
            if stalls >= 6:
                run.note('N-WANDER', f'move {i+1}', 'naive player stalled; last tries: ' + ', '.join(seen_labels[-6:]))
                run.frame(page, 'wander-stalled')
                return False
        else:
            stalls = 0
        if i % 4 == 0:
            run.frame(page, f'wander-{i+1}-{seen_labels[-1]}')
    run.note('N-WANDER', 'budget', f'naive player did not finish in {budget} moves')
    return False


def contact_sheet(run):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    frames = run.frames
    if not frames:
        return None
    ims = [Image.open(p) for p, _ in frames]
    tw = 220
    th = int(ims[0].height * tw / ims[0].width)
    cols = 6
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (tw + 8) + 8, rows * (th + 30) + 8), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (im, (_, label)) in enumerate(zip(ims, frames)):
        x = 8 + (i % cols) * (tw + 8)
        y = 8 + (i // cols) * (th + 30)
        sheet.paste(im.resize((tw, th)), (x, y))
        d.text((x, y + th + 4), f'{i+1:02d} {label}'[:34], fill='black')
    p = os.path.join(run.out, run.vp['name'] + '-sheet.png')
    sheet.save(p)
    return p


def run_play(game, hand=None, out='fingers-play', viewports=None, wander_mode=False):
    from playwright.sync_api import sync_playwright
    viewports = viewports or (hand.get('viewports') if hand else None) or VIEWPORTS
    results = []
    with sync_playwright() as p:
        exe = chromium_path()
        browser = p.chromium.launch(**({'executable_path': exe} if exe else {}))
        for vp in viewports:
            ctx = browser.new_context(viewport={'width': vp['width'], 'height': vp['height']},
                                      device_scale_factor=2, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            run = Run(out, vp)
            page.on('pageerror', lambda e, r=run: r.halt('P-ERROR', 'page', str(e)[:120]))
            page.goto('file://' + os.path.abspath(game))
            page.wait_for_timeout(500)
            if wander_mode:
                wander(page, run, end_sel=(hand or {}).get('end'))
            else:
                ok = play_hand(page, run, hand)
                if ok and hand.get('end'):
                    if not (page.locator(hand['end']).count() and page.locator(hand['end']).first.is_visible()):
                        run.halt('P-STUCK', 'end', f'playthrough finished but {hand["end"]} is not showing')
            sheet = contact_sheet(run)
            results.append((run, sheet))
            ctx.close()
        browser.close()
    return results


def report(game, results, mode):
    bad = 0
    print(f'\n  STUDIO FINGERS · PLAY ({mode}) — {os.path.basename(game)}')
    for run, sheet in results:
        vp = run.vp
        print(f'\n  [{vp["name"]}]  {len(run.frames)} frames' + (f'  sheet: {sheet}' if sheet else ''))
        # de-duplicate repeated findings from repeated taps
        seen = set()
        for code, where, msg in run.halts:
            k = (code, where.split(' (')[0], msg[:40])
            if k in seen: continue
            seen.add(k)
            print(f'    HALT {code:11s} {where}: {msg}')
        for code, where, msg in run.notes:
            k = (code, where.split(' (')[0], msg[:40])
            if k in seen: continue
            seen.add(k)
            print(f'    note {code:11s} {where}: {msg}')
        if run.trace:
            dead = sum(1 for t in run.trace if t.endswith('[no change]'))
            print(f'    wander: {len(run.trace)} moves, {dead} changed nothing. Path: ' + ' > '.join(t.replace('  [no change]','*') for t in run.trace[:40]))
            if dead:
                run.notes.append(('N-WANDER', 'dead taps', f'{dead} of {len(run.trace)} naive moves changed nothing (marked *)'))
        if run.halts:
            bad += 1
    print(f'\n  === {bad} of {len(results)} viewports at HALT ===')
    return bad


def self_test():
    """Canary: a tiny game where the post is clipped by a short feed box must HALT
    P-FOCUS; the same game with a tall box must pass. Blind is not clean."""
    import tempfile
    tpl = ('<!doctype html><meta name="viewport" content="width=device-width">'
           '<style>body{margin:0;font:18px sans-serif}#feed{height:%dpx;overflow:hidden}'
           '.post{height:300px;background:#ddd}button{width:100%%;height:60px}</style>'
           '<div id="feed"><div class="post" id="p">post <span id="n">0</span></div></div>'
           '<button id="b" onclick="document.getElementById(\'n\').textContent++">Boost</button>')
    hand = {'steps': [{'label': 'boost', 'focus': '#p', 'action': '#b'}],
            'viewports': [{'name': 'canary', 'width': 375, 'height': 667}]}
    tmp = tempfile.mkdtemp()
    ok = True
    for h, expect_halt in ((150, True), (320, False)):
        f = os.path.join(tmp, f'c{h}.html')
        open(f, 'w').write(tpl % h)
        res = run_play(f, hand, out=os.path.join(tmp, f'o{h}'))
        halted = any(c == 'P-FOCUS' for c, _, _ in res[0][0].halts)
        print(f'  canary feed {h}px: P-FOCUS {"HALT" if halted else "pass"} (expected {"HALT" if expect_halt else "pass"})')
        ok = ok and (halted == expect_halt)
    print('  SELF-TEST', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == '--self-test':
        sys.exit(self_test())
    game = a[0]
    out = a[a.index('--out') + 1] if '--out' in a else 'fingers-play'
    if '--hand' in a:
        hand = json.load(open(a[a.index('--hand') + 1]))
        res = run_play(game, hand, out=out)
        bad = report(game, res, 'hand')
        if '--wander' in a:
            res2 = run_play(game, hand, out=out + '-wander', wander_mode=True)
            report(game, res2, 'wander')
        sys.exit(1 if bad else 0)
    if '--wander' in a:
        res = run_play(game, None, out=out, wander_mode=True)
        report(game, res, 'wander')
        sys.exit(0)
    print(__doc__); sys.exit(2)


if __name__ == '__main__':
    main()
