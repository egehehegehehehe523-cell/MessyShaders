"""Runtime RGB pipeline probes without changing the default E-Lite visuals.

Stages are separate 3D image samplers because a successful GLSL compile
does not prove that Iris populated or executed a particular compute pass.
"""
from __future__ import annotations


def change(pack: dict[str, bytes], path: str, old: str, new: str) -> None:
    original = pack[path].decode("utf-8")
    if original.count(old) != 1:
        raise ValueError(f"RGB diagnostic anchor mismatch in {path}: {old[:80]!r}")
    pack[path] = original.replace(old, new, 1).encode("utf-8")


def apply_rgb_diagnostics(pack: dict[str, bytes]) -> dict:
    config = "shaders/lib/config.glsl"
    pack[config] += b"""
// Troubleshooting only. Zero keeps the exact old render path.
#define MESSY_RGB_DEBUG 0 // [0 1 2 3 4]
#define MESSY_RGB_LIVE_FIELD 0 // [0 1]
"""
    props = "shaders/shaders.properties"
    change(pack, props,
        "MESSY_AUTO_NORMAL_DEBUG PERF_IMPACT",
        "MESSY_AUTO_NORMAL_DEBUG MESSY_RGB_DEBUG MESSY_RGB_LIVE_FIELD PERF_IMPACT")
    change(pack, props,
        "sliders = ",
        "sliders = MESSY_RGB_DEBUG MESSY_RGB_LIVE_FIELD ")
    pack["shaders/lang/en_US.lang"] += (
        "\noption.MESSY_RGB_DEBUG=RGB Pipeline Diagnostic\n"
        "option.MESSY_RGB_DEBUG.comment=0 Normal; 1 Seed RGB (first pass); 2 Propagated RGB; 3 History RGB; 4 World-position coordinates. Test beside a sea lantern and turn off after screenshots.\n"
        "option.MESSY_RGB_LIVE_FIELD=Use Live RGB Field\n"
        "option.MESSY_RGB_LIVE_FIELD.comment=0 Use original filtered history; 1 bypass temporal history and read the current propagated RGB. If 1 restores colored light, the history pass is faulty.\n"
    ).encode()

    fragment = "shaders/common/solid_blocks_fragment.glsl"
    change(pack, fragment,
        '#include "/lib/messy_rgb_sample.glsl"',
        '#include "/lib/messy_rgb_sample.glsl"\n'
        'uniform sampler3D messyRgbASampler;\n'
        'uniform sampler3D messyRgbBSampler;')
    change(pack, fragment,
        "        vec3 messyRGB = messyAppliedRGB(messyLightUVW, frameCounter);",
        """        #if MESSY_RGB_LIVE_FIELD == 1
            // Same energy/outer-boundary gating as the filtered history.
            vec3 messyRGB = texture3D(messyRgbASampler, messyLightUVW).rgb;
            float messyRawEnergy = max(messyRGB.r, max(messyRGB.g, messyRGB.b));
            vec3 messyEdges = min(messyLightUVW, vec3(1.0) - messyLightUVW) * 48.0;
            float messyEdgeDistance = min(messyEdges.x, min(messyEdges.y, messyEdges.z));
            messyRGB *= smoothstep(0.08, 0.18, messyRawEnergy)
                      * smoothstep(0.75, 4.0, messyEdgeDistance);
        #else
            vec3 messyRGB = messyAppliedRGB(messyLightUVW, frameCounter);
        #endif""")
    change(pack, fragment,
        '    #include "/src/writebuffers.glsl"',
        """    #if MESSY_RGB_DEBUG > 0
        vec3 messyProbe = vec3(0.0);
        if (all(greaterThanEqual(messyLightUVW, vec3(0.0))) &&
            all(lessThan(messyLightUVW, vec3(1.0)))) {
            #if MESSY_RGB_DEBUG == 1
                messyProbe = texture3D(messyRgbBSampler, messyLightUVW).rgb;
            #elif MESSY_RGB_DEBUG == 2
                messyProbe = texture3D(messyRgbASampler, messyLightUVW).rgb;
            #elif MESSY_RGB_DEBUG == 3
                messyProbe = messySampleHistory(messyLightUVW, frameCounter);
            #elif MESSY_RGB_DEBUG == 4
                messyProbe = fract(messyLightUVW * 8.0);
            #endif
        }
        // Purple-black means this stage has no light; colored areas are
        // raw voxel RGB. Mode 4 should show stripes regardless of lights.
        block_color.rgb = vec3(0.03, 0.01, 0.05) + messyProbe * 3.0;
    #endif
    #include "/src/writebuffers.glsl" """.rstrip())
    return {
        "default_visual_change": False,
        "mode_1": "raw first-step RGB field B",
        "mode_2": "raw fully-propagated RGB field A",
        "mode_3": "temporally filtered RGB history",
        "mode_4": "world-relative UV bands / coordinate sanity check",
        "live_field_option": "bypass history for source/pass isolation",
        "gpu_benchmarked": False,
    }
