"""Linux rendered capture route: private Xvfb inside the existing Runner sandbox.

Godot's headless display uses the dummy renderer, not a screenshot renderer. Keep
Compatibility/OpenGL3 (the game's style lock); do not substitute a Vulkan renderer.
No host X/Wayland sockets, auth files or ambient display variables are exposed.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile

INSTALL = 'install xvfb (sudo apt install xvfb)'
_CACHE = {}

# This wrapper runs INSIDE Runner/bwrap, after both limit stages. Xvfb's socket is
# in bwrap's private /tmp. -ac is local to that namespace, and TCP is disabled.
XVFB = '''import os,select,subprocess,sys
r,w=os.pipe()
p=subprocess.Popen([sys.argv[1],'-displayfd',str(w),'-screen','0','640x480x24','-nolisten','tcp','-ac','-noreset'],
                   pass_fds=(w,),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=sys.stderr,env=dict(os.environ))
os.close(w)
if not select.select([r],[],[],10)[0]:
 p.terminate(); p.wait(); raise SystemExit('capture display: Xvfb startup timed out')
number=os.read(r,64).decode('ascii').strip(); os.close(r)
if not number.isdigit() or p.poll() is not None:
 raise SystemExit('capture display: Xvfb failed to provide a display')
e=dict(os.environ); e['DISPLAY']=':'+number; e['LIBGL_ALWAYS_SOFTWARE']='1'
try:
 result=subprocess.run(sys.argv[2:],env=e,stdin=subprocess.DEVNULL)
finally:
 p.terminate()
 try: p.wait(timeout=3)
 except subprocess.TimeoutExpired: p.kill(); p.wait()
raise SystemExit(result.returncode)
'''

SCRIPT = '''extends SceneTree
func _initialize():
    root.size = Vector2i(32, 32)
    var rect = ColorRect.new()
    rect.color = Color(0.2, 0.7, 0.4)
    rect.size = Vector2(32, 32)
    root.add_child(rect)
    await process_frame
    await RenderingServer.frame_post_draw
    var image = root.get_texture().get_image()
    if image == null or image.is_empty():
        quit(2)
        return
    var err = image.save_png("res://capture.png")
    print("CAPTURE_OK" if err == OK else "CAPTURE_FAILED")
    quit(0 if err == OK else 2)
'''


def command(argv, xvfb):
    """Same renderer as the game, with a fresh private X display; never --headless."""
    return [sys.executable, '-I', '-S', '-c', XVFB, xvfb, argv[0], '--display-driver', 'x11',
            '--rendering-method', 'gl_compatibility', '--rendering-driver', 'opengl3'] + list(argv[1:])


def probe(godot, xvfb):
    """A real tiny capture through Runner.run; available executables alone are not readiness."""
    from .runner import Runner
    from .safety import Fault, Project
    try:
        with tempfile.TemporaryDirectory(prefix='hermes64-display-') as tmp:
            project = Project(str(Path(tmp).resolve()), 'capture', create=True)
            root = project.root
            (root / 'project.godot').write_text('[application]\nconfig/name="Capture probe"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding='utf-8')
            (root / 'capture.gd').write_text(SCRIPT, encoding='utf-8')
            out = Runner(project).run(command([godot, '--path', str(root), '--script', 'res://capture.gd'], xvfb),
                                      root, timeout=30)
            png = root / 'capture.png'
            image = png.read_bytes() if png.is_file() else b''
            image_ok = False
            if image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) > 32:
                from .style_gate import read_png
                try:
                    width, height, pixels = read_png(png)
                    if width >= 32 and height >= 32:
                        red, green, blue = pixels[3 * (16 * width + 16):3 * (16 * width + 16) + 3]
                        image_ok = green > red + 30 and green > blue + 20
                except Exception:  # malformed PNG or no rendered green test rectangle: not a display pass
                    image_ok = False
            ok = out['returncode'] == 0 and 'CAPTURE_OK' in out['stdout'].split() and image_ok
            reason = 'tiny Compatibility/OpenGL3 PNG via Runner.run + private Xvfb' if ok else (
                'tiny capture failed (exit %s): %s' % (out['returncode'],
                ' '.join(out['stderr'].split())[-600:] or 'no rendered PNG / CAPTURE_OK marker'))
            return {'ok': ok, 'detail': reason, 'xvfb': xvfb}
    except (OSError, ValueError, Fault) as exc:
        return {'ok': False, 'detail': 'tiny capture could not run: ' + ' '.join(str(exc).split())[:600], 'xvfb': xvfb}


def status(settings=None, refresh=False):
    """Cached real-run result for this Godot/Xvfb binary pair. No downloads/installs."""
    from .runner import locate
    from .safety import Fault
    if os.environ.get('HERMES64_DISPLAY') == '0':
        return {'ok': False, 'detail': 'HERMES64_DISPLAY=0 (capture disabled)'}
    xvfb = shutil.which('Xvfb')
    if not xvfb:
        return {'ok': False, 'detail': 'Xvfb not found; ' + INSTALL}
    try:
        godot = locate('godot', (settings or {}).get('godot_path') or '')
    except Fault as exc:
        return {'ok': False, 'detail': str(exc)}
    def stamp(path):
        try:
            st = Path(path).stat()
            return str(path), st.st_mtime_ns, st.st_size
        except OSError:
            return str(path), None, None
    key = (stamp(godot), stamp(xvfb))
    if refresh or key not in _CACHE:
        _CACHE[key] = probe(godot, xvfb)
    return dict(_CACHE[key])


def prepare(argv, settings=None):
    """Capture argv, or a typed refusal before starting a game without a usable display."""
    from .safety import fail
    result = status(settings)
    if not result['ok']:
        fail('capture_display', 'not run: no display on this machine; ' + result['detail'])
    return command(argv, result['xvfb'])


def row(result):
    if result.get('ok'):
        return 'OK       capture display: ' + result['detail']
    return 'WARN     capture display: missing, ' + INSTALL + '; reason: ' + result.get('detail', 'not probed')
