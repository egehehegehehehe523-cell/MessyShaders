"""Neo-Voxy 0.5 Lite LOD shader-pair contract for MessyShaders.

The Lite pair uses E-Lite's own Voxy programs, with conservative distant
specular work avoidance. Shading differences are smoothly blended over
distance; water keeps original E-Lite behaviour so there is no hard water
material cut at the LOD boundary. No Voxy mod source or GPL-incompatible
shaderpack code is copied.
"""
from __future__ import annotations

CONTRACT = (
    "// VOXY_LITE_CONTRACT api=1;pack=MessyShaders E-Lite;"
    "versions=E-Lite-5.1.3-MessyShaders;transition=pack-distance-fade\n"
)

def patch_once(pack:dict[str,bytes],path:str,old:str,new:str):
    s=pack[path].decode("utf-8")
    if s.count(old)!=1:
        raise ValueError(f"Unexpected Lite shader anchor {path}: {s.count(old)}")
    pack[path]=s.replace(old,new,1).encode("utf-8")

def apply_lite_voxy(pack:dict[str,bytes])->dict:
    # Voxy 0.5 reads the pair relative to the active dimension directory.
    # All wrappers use exactly the same contract metadata.
    names=[]
    for dim in ("world0","world-1","world1",""):
        prefix=f"shaders/{dim}/" if dim else "shaders/"
        for kind in ("opaque","translucent"):
            old=f"{prefix}voxy_{kind}.glsl"
            new=f"{prefix}voxy_{kind}_lite.glsl"
            if new in pack:
                raise ValueError("Lite program already exists: "+new)
            if old not in pack:
                raise ValueError("Missing E-Lite Voxy base wrapper: "+old)
            source=pack[old].decode("utf-8")
            if source.count('#include "/common/')!=1:
                raise ValueError("Unexpected Voxy wrapper: "+old)
            source=CONTRACT+"#define MESSY_VOXY_LITE\n"+source
            pack[new]=source.encode("utf-8")
            names.append(new)

    # A real, limited Lite optimization: far from the near-chunk boundary,
    # skip nonessential specular texture work. Fade its visible effect as
    # distance grows, avoiding a sudden discontinuity at the first LOD ring.
    path="shaders/common/solid_voxy_blocks_fragment.glsl"
    old="""        float material_gloss_factor = materialGloss(reflect(viewPositionNormalized, normal), lmcoord, glossPower, normal) * glossFactor;"""
    new="""        float material_gloss_factor = 0.0;
        #ifdef MESSY_VOXY_LITE
            // Keep ordinary E-Lite material shading at the first LOD ring.
            // Smoothly remove distant specular work beyond the transition.
            float messyBoundaryDistance = float(vxRenderDistance * 16);
            float messyLiteGlossWeight = 1.0 - smoothstep(
                messyBoundaryDistance + 16.0,
                messyBoundaryDistance + 96.0,
                fogFragCoord);
            if (messyLiteGlossWeight > 0.001) {
                material_gloss_factor = materialGloss(
                    reflect(viewPositionNormalized, normal), lmcoord,
                    glossPower, normal) * glossFactor * messyLiteGlossWeight;
            }
        #else
            material_gloss_factor = materialGloss(
                reflect(viewPositionNormalized, normal), lmcoord,
                glossPower, normal) * glossFactor;
        #endif"""
    patch_once(pack,path,old,new)

    # E-Lite's historical patch JSON asks for a uniform present only in
    # later Minecraft versions. On the user's 1.21.1 build Voxy treats an
    # unbound requested uniform as a rendering error.
    meta="shaders/common/voxy.json"
    patch_once(pack,meta,
        '    "endFlashIntensity",',
        '    #if MC_VERSION >= 12109\n    "endFlashIntensity",\n    #endif')

    return {
        "contract":"api=1, pack-distance-fade",
        "paired_programs":names,
        "distant_optimization":"opaque specular disabled after smooth 16-96 block transition",
        "translucent":"original E-Lite water/refraction retained",
        "end_flash_uniform":"version-gated for Minecraft 1.21.9+",
        "caveats":[
            "Not the same optimizations as the Complementary Unbound/Euphoria Lite reference",
            "Runtime compilation and visual LOD seam must still be checked",
            "No Voxy source modifications or mixins",
        ],
    }
