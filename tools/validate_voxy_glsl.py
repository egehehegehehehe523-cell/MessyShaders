#!/usr/bin/env python3
"""Compile a minimal Neo-Voxy-like program using the *real* RGB helper.

Neo-Voxy injects sampler uniforms from voxy.json and uses core GLSL.
The regular E-Lite offline checker uses 430 compatibility and misses
duplicate uniform declarations and legacy texture3D on this path.
"""
from pathlib import Path
from zipfile import ZipFile
import sys


def extract_function(source: str, signature: str) -> str:
    """Extract one standalone GLSL function to compile with injected uniforms."""
    start = source.index(signature)
    opening = source.index("{", start)
    nesting = 1
    pos = opening + 1
    while nesting:
        if pos >= len(source):
            raise ValueError(f"Unterminated GLSL function {signature}")
        nesting += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos]

def main():
    pack, output = map(Path, sys.argv[1:3])
    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(pack) as z:
        lib = z.read("shaders/lib/messy_rgb_sample.glsl").decode("utf8")
        water = z.read("shaders/lib/water_voxy.glsl").decode("utf8")
        water_json = z.read("shaders/common/voxy.json").decode("utf8")
        assert '"vxDepthTexTrans": "sampler2D"' in water_json
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

    # Compile the actual E-Lite functions changed for Voxy's water depth and
    # normal continuity. Without this test, a missing sampler or an out-of-
    # scope variable in a global helper could pass all G-buffer smoke checks.
    water_source = (
        "#version 430 core\n"
        "#define texture2D texture\n"
        "#define WATER_ABSORPTION 0.05\n"
        "#define WATER_TURBULENCE 0.8\n"
        "uniform sampler2D vxDepthTexTrans, gaux1, noisetex;\n"
        "uniform float pixelSizeX, pixelSizeY, frameTimeCounter, rainStrength;\n"
        "uniform int isEyeInWater;\n"
        + "\n".join(extract_function(water, signature) for signature in (
            "vec3 normal_waves_voxy(",
            "vec3 refraction_voxy(",
            "vec3 get_normals_voxy(",
        ))
        + "\nlayout(location = 0) out vec4 color;\n"
        "void main() {\n"
        " vec3 bump = normal_waves_voxy(vec3(1.0));\n"
        " vec3 n = get_normals_voxy(bump, vec3(0.0, 1.0, 1.0),\n"
        "    vec3(1,0,0), vec3(0,0,1), vec3(0,1,0));\n"
        " color = vec4(refraction_voxy(n, vec3(0.4), bump), 1.0);\n"
        "}\n"
    )
    target = output / "voxy_water_depth.frag"
    target.write_text(water_source, encoding="utf8")
    print(target)

if __name__ == "__main__":
    main()
