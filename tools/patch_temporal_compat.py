"""Temporal RGB reprojection and actual generated-normal surface shading.

We preserve the existing 48^3 light propagation and blend its result through
two persistent 3-D history volumes. No Voxy/Minecraft/Colorwheel mixins.
Reference strategy: reprojection and bounded temporal persistence; all code
is independently authored. Blender accepts fresh light immediately and
decreases stale light over several frames to avoid voxel-step popping.
"""
from __future__ import annotations

SIZE=48

def replace_one(files:dict[str,bytes], path:str,old:str,new:str)->None:
    s=files[path].decode("utf-8")
    n=s.count(old)
    if n!=1:
        raise ValueError(f"Missing/duplicated anchor {path} ({n}): {old[:95]!r}")
    files[path]=s.replace(old,new,1).encode("utf-8")

def temporal_compute()->str:
    return """#version 430
layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;
const ivec3 workGroups = ivec3(6, 6, 48);
// Current fully propagated lighting from the existing six iterations.
layout(rgba16f) uniform readonly image3D messyRgbA;
// Two NON-clearing history images. Never read and write the same one.
layout(rgba16f) uniform image3D messyRgbHistoryA;
layout(rgba16f) uniform image3D messyRgbHistoryB;
uniform int frameCounter;
uniform vec3 cameraPosition;
uniform vec3 previousCameraPosition;

void main() {
    ivec3 p = ivec3(gl_GlobalInvocationID);
    if (any(greaterThanEqual(p, ivec3(48)))) return;
    vec3 fresh = max(imageLoad(messyRgbA, p).rgb, vec3(0.0));
    ivec3 shift = ivec3(floor(cameraPosition) - floor(previousCameraPosition));
    ivec3 previousCell = p + shift;
    bool valid = frameCounter > 0 &&
        all(greaterThanEqual(previousCell, ivec3(0))) &&
        all(lessThan(previousCell, ivec3(48))) &&
        all(lessThanEqual(abs(shift), ivec3(3)));
    vec3 result = fresh;
    if (valid) {
        vec3 oldLight = (frameCounter & 1) == 0
            ? imageLoad(messyRgbHistoryA, previousCell).rgb
            : imageLoad(messyRgbHistoryB, previousCell).rgb;
        oldLight = clamp(oldLight, vec3(0.0), vec3(8.0));
        // New light appears promptly, but falling and moving sources ease
        // out across frames. Reject large differences aggressively to
        // avoid strong trailing ghosts behind a fast-moving entity.
        vec3 difference = abs(fresh - oldLight);
        float gap = max(difference.r, max(difference.g, difference.b));
        float historyWeight = mix(0.64, 0.27, smoothstep(0.15, 0.80, gap));
        result = mix(fresh, oldLight, historyWeight);
        result = max(fresh, result); // Never delay a newly arriving source.
    }
    result = clamp(result, vec3(0.0), vec3(8.0));
    if ((frameCounter & 1) == 0)
        imageStore(messyRgbHistoryB, p, vec4(result, 1.0));
    else
        imageStore(messyRgbHistoryA, p, vec4(result, 1.0));
}
"""

def sample_lib()->str:
    return """// Generated MessyShaders shared RGB sample: terrain, Colorwheel, Voxy.
// Voxy generates uniforms from voxy.json. A second declaration here
// conflicts with Neo-Voxy's combined fragment shader.
#if !defined(VOXY_BLOCK) && !defined(VOXY_WATER)
uniform sampler3D messyRgbHistoryASampler;
uniform sampler3D messyRgbHistoryBSampler;
#endif

vec3 messyReadRGB(sampler3D sourceField, vec3 uv) {
    // Neo-Voxy and Colorwheel compile modern GLSL without texture3D().
#if defined(VOXY_BLOCK) || defined(VOXY_WATER) || defined(MESSY_COLORWHEEL)
    return texture(sourceField, uv).rgb;
#else
    return texture3D(sourceField, uv).rgb;
#endif
}
vec3 messySampleHistory(vec3 uv, int frameIndex) {
    if (any(lessThan(uv, vec3(0.0))) ||
        any(greaterThanEqual(uv, vec3(1.0)))) return vec3(0.0);
    return (frameIndex & 1) == 0
        ? messyReadRGB(messyRgbHistoryBSampler, uv)
        : messyReadRGB(messyRgbHistoryASampler, uv);
}
vec3 messyAppliedRGB(vec3 uv, int frameIndex) {
    vec3 rgb = max(messySampleHistory(uv, frameIndex), vec3(0.0));
    float energy = max(rgb.r, max(rgb.g, rgb.b));
    return rgb * smoothstep(0.045, 0.15, energy);
}
"""

def add_temporal(pack:dict[str,bytes])->dict:
    properties="shaders/shaders.properties"
    text=pack[properties].decode("utf-8")
    if "image.messyRgbHistoryA" in text: raise ValueError("Temporal images already exist")
    text+="""\n# Non-clearing temporal RGB volumes (two images, no read/write race).
image.messyRgbHistoryA = messyRgbHistoryASampler rgba rgba16f float false false 48 48 48
image.messyRgbHistoryB = messyRgbHistoryBSampler rgba rgba16f float false false 48 48 48
"""
    pack[properties]=text.encode("utf-8")
    lib="shaders/lib/messy_rgb_sample.glsl"
    if lib in pack: raise ValueError("Duplicate sample library")
    pack[lib]=sample_lib().encode("utf-8")
    for dim in ("world0","world-1","world1"):
        path=f"shaders/{dim}/prepare_g.csh"
        if path in pack:raise ValueError("Temporal pass collision: "+path)
        pack[path]=temporal_compute().encode("utf-8")
    # These samplers belong to a real field shared with Voxy and Colorwheel.
    path="shaders/common/solid_blocks_fragment.glsl"
    replace_one(pack,path,'uniform sampler3D messyRgbASampler;',
                '#include "/lib/messy_rgb_sample.glsl"')
    replace_one(pack,path,
                "vec3 messyRGB = texture3D(messyRgbASampler, messyLightUVW).rgb;",
                "vec3 messyRGB = messyAppliedRGB(messyLightUVW, frameCounter);")
    # The original energy gate was moved into the shared sample function.
    replace_one(pack,path, """        // Weak emitters dissipate perceptually within ~1-3 cells, while
        // full-strength placed lights retain their established footprint.
        float messyEnergy = max(messyRGB.r, max(messyRGB.g, messyRGB.b));
        messyRGB *= smoothstep(0.045, 0.15, messyEnergy);
""", "")
    return {"technique":"camera-cell reprojection; dual persistent 48^3 history images",
            "current_passes":8,
            "additional_compute_passes":1,
            "additional_vram_bytes":2*SIZE**3*8,
            "measured_gpu_cost":False,
            "notes":["Fast onset/short decay; not true subvoxel positions",
                     "Camera displacements above three blocks discard history",
                     "Shadow geometry still seeded independently per frame"]}

def fix_normals(pack:dict[str,bytes])->dict:
    # Surface normals were used for E-Lite's optional glossy path, but
    # diffuse/ambient stayed effectively flat under normal strength changes.
    # Make generated normals affect existing diffuse lighting *without*
    # additional texture samples, camera-fixed fake directional light or
    # parallax UV displacement.
    path="shaders/common/solid_blocks_fragment.glsl"
    anchor="    block_color.rgb *= mix(real_light, vec3(1.0), nightVision * 0.125);"
    shade="""    #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        // Only influence the directional surface lighting. Multiplying
        // ALL irradiance amplified per-pixel noise in ambient light, even at
        // night, and created the previously reported wrong-looking blocks.
        // Normals and sun/moon directions are both in view space.
        vec3 messyLightDirection = normalize(
            light_mix >= 0.5 ? sunPosition : moonPosition);
        vec3 messyNormal = normalize(bumpedNormal);
        vec3 messyOriginalNormal = normalize(flat_normal);
        float messyNewDiffuse = max(0.0, dot(messyNormal, messyLightDirection));
        float messyOriginalDiffuse = max(0.0, dot(messyOriginalNormal, messyLightDirection));
        float messyDelta = clamp(messyNewDiffuse - messyOriginalDiffuse, -0.20, 0.20);
        float messyDirectMask = clamp(visible_sky * max(0.0, directLight2), 0.0, 1.0);
        // This limits the maximum light-level change to +/- 12 percent.
        // Stronger "raised" relief requires actual authored height maps.
        float messyDiffuseFactor = clamp(
            1.0 + messyDelta * messyDirectMask * 0.60, 0.88, 1.12);
        real_light *= messyDiffuseFactor;
    #endif
"""
    replace_one(pack,path,anchor,shade+anchor)
    # Before this the RGB volume's relief shader used a constant light
    # direction in view space; that changed if the user merely rotated
    # the camera. Remove it: one consistent material-lighting path only.
    replace_one(pack,path, """        #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
            vec3 messyN = normalize(bumpedNormal);
            vec3 messyFlatN = normalize(flat_normal);
            vec3 messyLightDir = normalize(vec3(0.35, 0.82, 0.40));
            float messySurfaceRelief = clamp(
                dot(messyN - messyFlatN, messyLightDir), -0.35, 0.35);
            messyRGB *= (1.0 + 0.35 * messySurfaceRelief);
        #endif""","")
    # E-Lite 5.1.3 left gloss undefined on non-reflective block types.
    # NVIDIA specifically reports it as potentially uninitialized in the
    # user's run. Random undefined specular values could amplify normal
    # artifacts and should never enter computeRealLight.
    replace_one(pack,path,
                "        vec3 gloss;\n        if(block_type != 1.0){",
                "        vec3 gloss = vec3(0.0);\n        if(block_type != 1.0){")
    return {"visual_shading":"generated normal changes direct-lit RGB by at most 12% while preserving ambient brightness",
            "extra_texture_reads":0,
            "removed_camera_fixed_fake_direction":True,
            "labpbr_priority_retained":True}

def apply_temporal_normals(pack:dict[str,bytes])->dict:
    return {"temporal_rgb":add_temporal(pack),"generated_normals":fix_normals(pack)}
