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
    # Native Colorwheel shadow pass, based on its documented shaderpack API.
    # Use an explicit matched vertex/fragment interface. No references to
    # E-Lite's shadow_fragment.glsl (which declares a visible_sky varying that
    # E-Lite's normal shadow vertex never actually outputs).
    "shaders/clrwl_shadow.vsh": """#version 430 compatibility
#include "/lib/config.glsl"
out vec2 messyShadowUV;
out vec4 messyShadowTint;
void main() {
    gl_Position = ftransform();
    // Match E-Lite's shadow-clip distortion or moving contraption shadows
    // will not line up with shadows from ordinary terrain and block entities.
    float messyShadowDist = length(gl_Position.xy);
    float messyShadowFalloff = 1.0 / (1.0 + messyShadowDist);
    float messyShadowDistort = mix(1.0, messyShadowDist,
        SHADOW_DIST * messyShadowFalloff);
    gl_Position.xy /= messyShadowDistort;
    gl_Position.z *= 0.2;
    messyShadowUV = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    messyShadowTint = gl_Color;
}
""",
    "shaders/clrwl_shadow.fsh": """#version 430 compatibility
uniform sampler2D gtexture;
in vec2 messyShadowUV;
in vec4 messyShadowTint;
/* DRAWBUFFERS:0 */
layout(location=0) out vec4 messyShadowColor;
#ifdef MESSY_OFFLINE_TEST
void clrwl_computeFragment(in vec4 src, out vec4 color,
                           out vec2 lm, out float ao, out vec4 overlay) {
    color=src; lm=vec2(0.96875); ao=1.0; overlay=vec4(0.0);
}
#endif
void main() {
    vec4 sampleColor = texture(gtexture, messyShadowUV);
    if (sampleColor.a * messyShadowTint.a < 0.1) discard;
    vec2 lm; float ao; vec4 overlay;
    clrwl_computeFragment(sampleColor, messyShadowColor, lm, ao, overlay);
    if (messyShadowColor.a < 0.1) discard;
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
