# -*- coding: utf-8 -*-
"""Re-zip a .pptx with deflate.

pptxgenjs writes its parts with little or no compression, which left the deck at 693 KB against
93 KB for the same content. The theme step used to re-zip as a side effect and hid this; with that
step unavailable the deck has to be compressed explicitly. Content is byte-identical either way.
"""
import shutil
import sys
import zipfile
from pathlib import Path

src = Path(sys.argv[1])
tmp = src.with_suffix(".repack.pptx")
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
    # [Content_Types].xml must stay first for the package to be readable.
    names = zin.namelist()
    order = sorted(names, key=lambda n: (n != "[Content_Types].xml",))
    for n in order:
        # Read BEFORE touching compress_type: getinfo returns the reader's own ZipInfo, so
        # setting it first makes zin.read try to inflate a STORED entry and fail.
        data = zin.read(n)
        src_info = zin.getinfo(n)
        info = zipfile.ZipInfo(n, date_time=src_info.date_time)
        info.external_attr = src_info.external_attr
        # writestr honours the ZipInfo's own compress_type, not the archive default, so a
        # verbatim copy would stay STORED and the repack would do nothing.
        info.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(info, data)
before, after = src.stat().st_size, tmp.stat().st_size
shutil.move(str(tmp), str(src))
print("%s: %.0f KB -> %.0f KB" % (src.name, before / 1024, after / 1024))
