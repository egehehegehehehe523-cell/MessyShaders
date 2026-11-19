"""Shared Voxy/Colorwheel RGB interoperability for E-Lite-based MessyShaders.

Keep native Voxy opaque/translucent programs and feed their *nearby* terrain
with the same temporally filtered RGB field. Add native Colorwheel Flywheel
render programs, avoiding a second shader pack or competing patcher. Shader
code is original, not copied from Complementary's restricted sources.
"""
from __future__ import annotations
import re

def patch_once(pack,path,needle,sub):
    if path not in pack:raise ValueError(f"Missing shader program {path}")
    txt=pack[path].decode("utf-8")
    if txt.count(needle)!=1:raise ValueError(f"Expected unique anchor in {path}: {needle[:96]!r} (found {txt.count(needle)})")
    pack[path]=txt.replace(needle,sub,1).encode("utf-8")

COLORWHEEL_VERTEX = """#version 430 compatibility
// MessyShaders original Colorwheel/Flywheel fast vertex program.
uniform mat4 gbufferModelViewInverse;
out vec2 messyTexcoord;
out vec3 messyWorldRel;
void main() {
    vec4 viewPosition = gl_ModelViewMatrix * gl_Vertex;
    gl_Position = gl_ProjectionMatrix * viewPosition;
    messyTexcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    messyWorldRel = (gbufferModelViewInverse * viewPosition).xyz;
}
"""

COLORWHEEL_FRAGMENT = """#version 430 compatibility
// One shared colour-light sample; Colorwheel supplies material fragment,
// cutout, AO, light and overlay operations through clrwl_computeFragment.
uniform sampler2D gtexture;
uniform sampler2D lightmap;
uniform vec3 cameraPosition;
uniform int frameCounter;
in vec2 messyTexcoord;
in vec3 messyWorldRel;
#include "/lib/messy_rgb_sample.glsl"

/* DRAWBUFFERS:1 */
layout(location=0) out vec4 messyColor;

#ifdef MESSY_OFFLINE_TEST
void clrwl_computeFragment(in vec4 src, out vec4 color,
                           out vec2 lm, out float ao, out vec4 overlay) {
    color=src; lm=vec2(0.96875); ao=1.0; overlay=vec4(0.0);
}
#endif

void main() {
    vec4 source = texture2D(gtexture, messyTexcoord);
    vec2 lightCoord;
    float ao;
    vec4 overlay;
    clrwl_computeFragment(source, messyColor, lightCoord, ao, overlay);
    messyColor.rgb = mix(messyColor.rgb, overlay.rgb, overlay.a);
    vec3 vanillaLight = texture2D(lightmap, clamp(lightCoord,vec2(0.0),vec2(1.0))).rgb;
    vec3 voxelUV = (messyWorldRel + fract(cameraPosition) + vec3(24.0)) / 48.0;
    vec3 coloredLight = messyAppliedRGB(voxelUV, frameCounter);
    messyColor.rgb *= max(vec3(0.035), vanillaLight + coloredLight * 1.2);
    messyColor = clamp(messyColor, vec4(0.0), vec4(50.0));
}
"""

COLORWHEEL_SHADOW_VERTEX = """#version 430 compatibility
// Colorwheel shadow + emission capture; no independent Voxy/Minecraft hook.
uniform mat4 shadowModelViewInverse;
uniform vec3 cameraPosition;
attribute vec4 mc_Entity;
layout(r32ui) uniform uimage3D messyEmitVolume;
out vec2 messyTexcoord;
void main() {
    vec4 viewPosition = gl_ModelViewMatrix * gl_Vertex;
    gl_Position = gl_ProjectionMatrix * viewPosition;
    messyTexcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    // Only classified emissive Create contraption geometry. Avoid blanket
    // solid occupancy as instanced positions and cutout masks are approximate.
    int materialId = int(mc_Entity.x);
    if (materialId >= 26000 && materialId <= 26012) {
        vec3 cameraRelative = (shadowModelViewInverse * viewPosition).xyz;
        ivec3 voxel = ivec3(floor(cameraRelative + fract(cameraPosition) + 24.0));
        if (all(greaterThanEqual(voxel,ivec3(0))) &&
            all(lessThan(voxel,ivec3(48)))) {
            imageAtomicMax(messyEmitVolume, voxel,
                           (15u << 8u) | uint(materialId - 25999));
        }
    }
}
"""

COLORWHEEL_SHADOW_FRAGMENT = """#version 430 compatibility
uniform sampler2D gtexture;
in vec2 messyTexcoord;
/* DRAWBUFFERS:0 */
layout(location=0) out vec4 messyShadow;
#ifdef MESSY_OFFLINE_TEST
void clrwl_computeFragment(in vec4 src, out vec4 color,
                           out vec2 lm, out float ao, out vec4 overlay) {
    color=src; lm=vec2(0.96875); ao=1.0; overlay=vec4(0.0);
}
#endif
void main() {
    vec4 sampleColor=texture2D(gtexture,messyTexcoord);
    vec2 lm; float ao; vec4 overlay;
    clrwl_computeFragment(sampleColor,messyShadow,lm,ao,overlay);
}
"""

COLORWHEEL_PROPERTIES = """# MessyShaders native support for Colorwheel + Flywheel/Create.
# E-Lite writes its opaque scene colour to colortex1.
# The RGB field is shared with vanilla and Voxy, not copied.
oit = true
oit.gbuffers.coefficientRanks = 3
oit.gbuffers.colortex1 = 0
oit.shadow.shadowcolor0 = frontmost
oit.shadow.shadowcolor0.format = RGBA8
# Do not enable additional shadow occlusion culling until distortion
# passes are available and confirmed against the active Colorwheel version.
shadow.occlusion.culling = false
"""

def add_colorwheel(pack:dict[str,bytes])->dict:
    additions = {
        "shaders/clrwl_gbuffers.vsh":COLORWHEEL_VERTEX,
        "shaders/clrwl_gbuffers.fsh":COLORWHEEL_FRAGMENT,
        "shaders/clrwl_shadow.vsh":COLORWHEEL_SHADOW_VERTEX,
        "shaders/clrwl_shadow.fsh":COLORWHEEL_SHADOW_FRAGMENT,
        "shaders/colorwheel.properties":COLORWHEEL_PROPERTIES,
    }
    for path,code in additions.items():
        if path in pack:raise ValueError(f"Would overwrite existing Colorwheel program {path}")
        pack[path]=code.encode("utf-8")
    return {"native_programs":list(additions.keys()),
            "oit":"one coefficient buffer for colortex1, shadow frontmost",
            "rgb_light":"shared temporal voxel field",
            "limitation":"Flywheel material normals and occlusion require in-game validation"}

def add_voxy(pack:dict[str,bytes])->dict:
    opaque="shaders/common/solid_voxy_blocks_fragment.glsl"
    meta="shaders/common/voxy.json"
    if opaque not in pack or meta not in pack:
        raise ValueError("E-Lite native Voxy files missing; refusing fake compatibility")
    patch_once(pack,opaque,'#include "/lib/luma.glsl"',
               '#include "/lib/luma.glsl"\n#include "/lib/messy_rgb_sample.glsl"')
    anchor="    blockColor.rgb *= mix(realLight, vec3(1.0), nightVision * 0.125);"
    shade="""    // Voxy's original opaque path keeps its fog, depth and lighting.
    // Only inside the same nearby 48-block RGB volume add the shared light.
    // Beyond that volume unchanged native Voxy LOD lighting is retained.
    vec3 messyVoxyWorldRel = (vxModelViewInv * viewPosition).xyz;
    vec3 messyVoxyUVW =
        (messyVoxyWorldRel + fract(cameraPosition) + vec3(24.0)) / 48.0;
    realLight += messyAppliedRGB(messyVoxyUVW, frameCounter) * 1.2;
"""
    patch_once(pack,opaque,anchor,shade+anchor)
    # Preserve E-Lite's Voxy water/refraction path. Only add the shared
    # near-camera light to its three existing water/translucent light sums.
    water="shaders/common/water_voxy_blocks_fragment.glsl"
    patch_once(pack,water,'#include "/lib/luma.glsl"',
               '#include "/lib/luma.glsl"\n#include "/lib/messy_rgb_sample.glsl"')
    patch_once(pack,water,
               "    vec4 worldPos = vxModelViewInv * viewSpacePos4D;",
               """    vec4 worldPos = vxModelViewInv * viewSpacePos4D;
    vec3 messyWaterUVW = (worldPos.xyz + fract(cameraPosition) + vec3(24.0)) / 48.0;
    vec3 messyWaterRGB = messyAppliedRGB(messyWaterUVW, frameCounter) * 1.2;""")
    water_body=pack[water].decode("utf-8")
    water_body,count=re.subn(
        r"(?m)^([ \\t]*)candleColor;", 
        lambda match: match.group(1)+"candleColor + messyWaterRGB;",
        water_body)
    if count != 3:
        raise ValueError("Unexpected E-Lite Voxy translucent light assignment count: "+str(count))
    pack[water]=water_body.encode("utf-8")
    patch_once(pack,meta,'"frameTimeCounter",', '"frameTimeCounter",\n    "frameCounter",')
    patch_once(pack,meta,'"noisetex": "sampler2D",',
               '"noisetex": "sampler2D",\n'
               '    "messyRgbHistoryASampler": "sampler3D",\n'
               '    "messyRgbHistoryBSampler": "sampler3D",')
    return {"uses_native_e_lite_voxy":True,
            "added_uniform":"frameCounter",
            "samplers":["messyRgbHistoryASampler","messyRgbHistoryBSampler"],
            "scope":"nearby opaque and translucent Voxy geometry; distant LODs unchanged",
            "limitations":["No extra 3D voxelization of distant Voxy chunks",
                           "No Voxy source edits/mixins",
                           "Voxy custom sampler binding needs in-game verification"]}

def apply_render_compat(pack:dict[str,bytes])->dict:
    return {"colorwheel":add_colorwheel(pack),"voxy":add_voxy(pack)}
