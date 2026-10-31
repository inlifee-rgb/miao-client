# -*- coding: utf-8 -*-
import os, subprocess
from PIL import Image

src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app-icon.png')
out_icns = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.icns')
setdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.iconset')

os.makedirs(setdir, exist_ok=True)
im = Image.open(src).convert('RGBA')
for s in (16, 32, 128, 256, 512):
    im.resize((s, s), Image.LANCZOS).save(os.path.join(setdir, 'icon_%dx%d.png' % (s, s)))
    im.resize((s * 2, s * 2), Image.LANCZOS).save(os.path.join(setdir, 'icon_%dx%d@2x.png' % (s, s)))
subprocess.run(['iconutil', '-c', 'icns', setdir, '-o', out_icns], check=True)
print('生成', out_icns)
