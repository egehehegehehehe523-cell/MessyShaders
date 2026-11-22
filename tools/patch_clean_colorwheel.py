"""Colorwheel/Flywheel native shader programs without the removed RGB volume.

Keeps the Colorwheel shader API and ordinary E-Lite lightmap illumination.
No custom lighting image, compute pass, or extra shader dependency.
"""
from __future__ import annotations


PROGRAMS = {
    "shaders/clrwl_gbuffers.vsh": """#version 430 compatibility
out vec2 messyUV;
void main() {
    gl_Position = ftransform();
    messyUV = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
}
""",
    "shaders/clrwl_gbuffers.fsh": """#version 430 compatibility
uniform sampler2D gtexture;
uniform sampler2D lightmap;
in vec2 messyUV;
/* DRAWBUFFERS:1 */
layout(location=0) out vec4 messyColor;
// clrwl_computeFragment is provided by Colorwheel at shader compilation.
#ifdef MESSY_OFFLINE_TEST
void clrwl_computeFragment(in vec4 src, out vec4 color,
                           out vec2 lm, out float ao, out vec4 overlay) {
    color=src; lm=vec2(0.96875); ao=1.0; overlay=vec4(0.0);
}
#endif
void main() {
    vec2 lm; float ao; vec4 overlay;
    clrwl_computeFragment(texture(gtexture, messyUV), messyColor, lm, ao, overlay);
    messyColor.rgb = mix(messyColor.rgb, overlay.rgb, overlay.a);
    messyColor.rgb *= max(vec3(0.035), texture(lightmap, clamp(lm, 0.0, 1.0)).rgb);
    messyColor.rgb *= clamp(ao, 0.0, 1.0);
}
""",
    "shaders/colorwheel.properties": """# Colorwheel's native Flywheel shader path.
# E-Lite does not write the coefficient buffers needed for Colorwheel OIT.
# Requesting them without the matching shaders can produce a broken-pack warning.
oit = false
shadow.occlusion.culling = false
""",
}


def apply(pack: dict[str, bytes]) -> None:
    for path, code in PROGRAMS.items():
        if path in pack:
            raise ValueError(f"Existing Colorwheel file: {path}")
        pack[path] = code.encode("utf-8")
