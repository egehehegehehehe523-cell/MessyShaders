"""Expand dynamic emitter coverage and add independent coated-texture detail.

Euphoria classifications are MIT-licensed metadata, not Complementary GLSL.
This patch is run *after* the existing RGB and procedural PBR stages.
"""
from __future__ import annotations
from pathlib import Path
import re

# Existing local palette-index and entity IDs are never renumbered.
# Not all entities in these broad Euphoria groups are physically luminous.
# This matches categories, not their dynamic state or animated emissive pixels.
EUPHORIA_GROUP_TO_LOCAL = {
    50000: 26202, 50008: 26211, 50020: 26200,
    50028: 26212, 50048: 26201, 50052: 26206,
    50056: 26213, 50060: 26209, 50072: 26210,
    50080: 26208, 50088: 26221, 50092: 26214,
    50100: 26215, 50108: 26216, 50116: 26217,
    50120: 26218, 50124: 26219, 50140: 26220,
    50144: 26222, 50148: 26204,
}

EXTRA_VANILLA_CATEGORIES = {
    26208: ("light_blue", "allay"),
    26209: ("cyan", "vex"),
    26210: ("yellow", "experience_orb"),
    26211: ("purple", "enderman"),
    26212: ("cyan", "drowned"),
    26213: ("light_blue", "stray"),
    26214: ("cyan", "trident"),
    26215: ("green", "bogged"),
    26216: ("orange", "creaking"),
    26217: ("orange", "copper_golem"),
    26218: ("orange", "parched"),
    26219: ("cyan", "zombie_nautilus"),
    26220: ("yellow", "spectral_arrow"),
    26221: ("orange", "entity_flame"),
    26222: ("green", "eye_of_ender"),
}

PALETTE_INDEX = {
    "white": 1, "brown": 2, "red": 3, "orange": 4, "yellow": 5,
    "lime": 6, "green": 7, "cyan": 8, "light_blue": 9, "blue": 10,
    "purple": 11, "magenta": 12, "pink": 13,
}

def replace_once(payload: dict[str, bytes], path: str, before: str, after: str):
    text = payload[path].decode("utf-8")
    count = text.count(before)
    if count != 1:
        raise ValueError(f"Patch anchor mismatch {path}: {count} occurrences of {before[:90]!r}")
    payload[path] = text.replace(before, after, 1).encode("utf-8")

def parse_entities(text: str) -> dict[int, list[str]]:
    # 1.21 section first, older entries are duplicate fallback and ignored.
    logical = re.sub(r"\\\s*\n", " ", text)
    out: dict[int, list[str]] = {}
    for line in logical.splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^entity\.(\d+)\s*=\s*(.*)", line)
        if m:
            out.setdefault(int(m[1]), m.group(2).split())
    return out

def norm(name: str) -> str:
    return name if ":" in name else "minecraft:" + name

def expand_entities(pack: dict[str, bytes], euphoria_root: Path | None):
    # E-Lite maps a few of the same vanilla entities under other IDs.
    # Preserve those IDs rather than duplicate the property assignment.
    path="shaders/entity.properties"
    old = pack[path].decode("utf-8")
    known = parse_entities(old)
    seen = {norm(token) for names in known.values() for token in names}

    grouped: dict[int, list[str]] = {
        key: value.split() for key, (_, value) in EXTRA_VANILLA_CATEGORIES.items()
    }
    stats = {"mit_entity_groups": 0, "modded_candidates": 0}
    if euphoria_root is not None:
        props = euphoria_root / "entity.properties"
        source = parse_entities(props.read_text(encoding="utf-8-sig"))
        for upstream, dest in EUPHORIA_GROUP_TO_LOCAL.items():
            members=source.get(upstream, [])
            grouped.setdefault(dest, []).extend(members)
            stats["mit_entity_groups"] += bool(members)

    # Existing local IDs 26200..26207 are expanded too: append a *single*
    # additional definition only for IDs that were not present before.
    additional: dict[int, list[str]] = {}
    for local, names in grouped.items():
        # Existing mappings 26200..26207 are appended to, not redefined.
        if local in known:
            continue
        clean=[]
        for name in names:
            key=norm(name)
            if key not in seen and name not in clean:
                clean.append(name)
                seen.add(key)
                if ":" in key and not key.startswith("minecraft:"):
                    stats["modded_candidates"]+=1
        additional[local]=clean

    # For Euphoria categories sharing pre-existing local IDs, edit the
    # original assignment in-place: don't append conflicting entity.N lines.
    # Keep the first occurrence of the id.
    for upstream, local in EUPHORIA_GROUP_TO_LOCAL.items():
        if local not in known or euphoria_root is None:
            continue
        members = parse_entities(
            (euphoria_root / "entity.properties").read_text(encoding="utf-8-sig")
        ).get(upstream, [])
        additions=[]
        for name in members:
            key=norm(name)
            if key not in seen:
                additions.append(name)
                seen.add(key)
                if ":" in key and not key.startswith("minecraft:"):
                    stats["modded_candidates"]+=1
        if additions:
            # E-Lite/custom local ID entries are single-line definitions.
            pattern=re.compile(r"(?m)^(entity\."+str(local)+r"\s*=\s*[^\n]*)$")
            old,n=pattern.subn(lambda m:m.group(1)+" "+" ".join(additions),old,count=1)
            if n != 1: raise ValueError(f"Missing entity declaration {local}")

    for local,names in sorted(additional.items()):
        if names:
            old+=f"\nentity.{local} = "+" ".join(names)
    pack[path]=(old.rstrip()+"\n").encode("utf-8")
    return stats

def moving_light_glsl(pack: dict[str, bytes]):
    # Use a broader set of entity IDs *without* lifting Complementary's code.
    path="shaders/lib/messy_voxel_vertex.glsl"
    palette="\n".join(
        f"    if (entity == {eid}) return {PALETTE_INDEX[color]}u;"
        for eid,(color,_) in EXTRA_VANILLA_CATEGORIES.items())
    anchor="    // E-Lite already maps lightning to 10101. Retain its classification.\n    if (entity == 10101) return 1u;"
    replace_once(pack,path,anchor,
        palette+"\n"
        "    // Original E-Lite mappings are kept: flames and drowned already\n"
        "    // have their own IDs. Only an actual flame render emits orange.\n"
        "    if (entity == 10201) return 4u; // entity_flame\n"
        "    if (entity == 10200) return 8u; // drowned\n"
        "    if (entity == 10101) return 1u; // lightning")
    anchor2=("    if (currentRenderedItemId >= 26100 && currentRenderedItemId <= 26112)\n"
             "        index = uint(currentRenderedItemId - 26099);\n"
             "    else\n"
             "        index = messyEntityColorIndex(entityId);")
    replace_once(pack,path,anchor2,
             "    if (currentRenderedItemId >= 26100 && currentRenderedItemId <= 26112)\n"
             "        index = uint(currentRenderedItemId - 26099);\n"
             "    else if (currentRenderedItemId >= 26000 && currentRenderedItemId <= 26012)\n"
             "        index = uint(currentRenderedItemId - 25999); // luminous block as dropped item\n"
             "    else\n"
             "        index = messyEntityColorIndex(entityId);")

def coated_textures(pack: dict[str, bytes]):
    # The effect is deterministic procedural texture-grain, NOT a clearcoat
    # material, and requires no extra texture lookup/pass.
    path="shaders/common/solid_blocks_fragment.glsl"
    anchor="    lowp float block_luma = luma(block_color.rgb);"
    coat=StringPatchCoat = '''
    #if defined MESSY_COATED_TEXTURES && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        // Sprite-local micrograin: cheap arithmetic and no additional map.
        // Keep atlas tessellation and mip filtering stable on modded textures.
        vec2 messyCoatPx = floor(final_uv * vec2(atlasSize) * 1.5);
        vec3 messyHashP = fract(vec3(messyCoatPx.xyx) * vec3(0.1031, 0.11369, 0.13787));
        messyHashP += dot(messyHashP, messyHashP.yzx + 19.19);
        float messyGrain = fract((messyHashP.x + messyHashP.y) * messyHashP.z);
        float messyMipFade = 1.0 - smoothstep(1.5, 5.0,
            log2(max(1.0, length(vec2(atlasSize) * fwidth(final_uv)))));
        float messyContrast = 1.0 - clamp(block_luma, 0.0, 1.0);
        block_color.rgb *= 1.0 +
            (messyGrain - 0.5) * MESSY_COAT_STRENGTH * messyContrast * messyMipFade;
    #endif
'''
    replace_once(pack,path,anchor,anchor+"\n"+coat)

    # Atlas dimensions are needed even when generated PBR is off.
    replace_once(pack,path,
                 "#ifdef MESSY_IPBR\nuniform ivec2 atlasSize;\n#endif",
                 "#if defined(MESSY_IPBR) || defined(MESSY_COATED_TEXTURES)\nuniform ivec2 atlasSize;\n#endif")
    config="shaders/lib/config.glsl"
    pack[config]=((
        "#define MESSY_COATED_TEXTURES\n"
        "#define MESSY_COAT_STRENGTH 0.18 // [0.0 0.08 0.12 0.18 0.24 0.32]\n"
        )+pack[config].decode("utf-8")).encode("utf-8")

    props="shaders/shaders.properties"
    replace_once(pack,props,
        "MESSY_IPBR_RELIEF_DEPTH <empty> PERF_IMPACT",
        "MESSY_IPBR_RELIEF_DEPTH MESSY_COATED_TEXTURES MESSY_COAT_STRENGTH PERF_IMPACT")

    # Existing English translations are complemented, not overwritten.
    lang="shaders/lang/en_US.lang"
    existing=pack.get(lang,b"").decode("utf-8")
    existing+="\n# MessyShaders experimental feature names\n"
    for k,v in {
        "screen.MESSY_FEATURES":"Messy Features",
        "option.MESSY_DYNAMIC_EMITTERS":"Moving Coloured Lights",
        "option.MESSY_IPBR":"Generated PBR",
        "option.MESSY_IPBR_NORMAL_STRENGTH":"Normal Map Strength",
        "option.MESSY_IPBR_RELIEF":"Raised Texture Depth",
        "option.MESSY_IPBR_RELIEF_DEPTH":"Relief Depth",
        "option.MESSY_COATED_TEXTURES":"Coated Textures",
        "option.MESSY_COAT_STRENGTH":"Coating Strength",
    }.items():
        existing+=f"{k}={v}\n"
    pack[lang]=existing.encode("utf-8")

def patch_full_coverage_coating(pack: dict[str,bytes], euphoria_root: Path | None) -> dict:
    moving_light_glsl(pack)
    euphoria_stats=expand_entities(pack,euphoria_root)
    coated_textures(pack)
    return {
        "entity_classification":euphoria_stats,
        "dynamic_block_item_fallback":True,
        "fire_pseudo_entity_compat":True,
        "coated_textures":{"type":"independent atlas micrograin (not clearcoat)",
                           "extra_texture_fetches":0,"gpu_benchmarked":False},
        "limitations":["Only shadow-rendered entities/items can be illuminated",
                       "Broad MIT entity category matching may include non-emissive mobs",
                       "No burning-NBT detection for arrows/mobs",
                       "No in-game validation of parallax or micrograin yet"]
    }
