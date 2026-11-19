#!/usr/bin/env python3
"""Compile a minimal Neo-Voxy-like program using the *real* RGB helper.

Neo-Voxy injects sampler uniforms from voxy.json and uses core GLSL.
The regular E-Lite offline checker uses 430 compatibility and misses
duplicate uniform declarations and legacy texture3D on this path.
"""
from pathlib import Path
from zipfile import ZipFile
import sys

def main():
    pack, output = map(Path, sys.argv[1:3])
    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(pack) as z:
        lib = z.read("shaders/lib/messy_rgb_sample.glsl").decode("utf8")
        names = set(z.namelist())
        for dim in ("world0", "world-1", "world1", ""):
            prefix = f"shaders/{dim}/" if dim else "shaders/"
            assert prefix+"voxy_opaque_lite.glsl" in names
            assert prefix+"voxy_translucent_lite.glsl" in names
        assert "image.messyRgbHistoryA" in z.read("shaders/shaders.properties").decode("utf8")
        assert '#if MC_VERSION >= 12109' in z.read("shaders/common/voxy.json").decode("utf8")
    for tag in ("VOXY_BLOCK", "VOXY_WATER"):
        source = (
            "#version 430 core\n"
            f"#define {tag} 1\n"
            "// These are already declared by Neo-Voxy based on voxy.json.\n"
            "uniform sampler3D messyRgbHistoryASampler;\n"
            "uniform sampler3D messyRgbHistoryBSampler;\n"
            "uniform int frameCounter;\n"
            + lib +
            "\nlayout(location = 0) out vec4 color;\n"
            "void main() { color = vec4(messyAppliedRGB(vec3(0.5), frameCounter), 1.0); }\n"
        )
        filename=output/f"voxy_{tag.lower()}.frag"
        filename.write_text(source,encoding="utf8")
        print(filename)

if __name__ == "__main__":
    main()
