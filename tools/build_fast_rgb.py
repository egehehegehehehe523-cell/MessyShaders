#!/usr/bin/env python3
"""Build the first *experimental* MessyShaders lighting branch.

Repackages the supplied LGPL E-Lite 5.1.3 shader archive, adding a cheap,
vertex-based RGB held-item light and colored emitter surfaces.  This is NOT
voxel-propagated RGB light, source occlusion, IntegratedPBR+, or a Luxium port.
Euphoria's optional MIT-licensed classification data is processed at build
time.  No Complementary, Euphoria shader or Luxium renderer code is copied.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "§lE-LITE shaders 5.1.3.zip"
OUTPUT = ROOT / "dist" / "MessyShaders-RGB-experimental.zip"

# Authored independent palette, not a copy of Complementary's numeric colors.
PALETTE = {
    "white": (1.00, 0.98, 0.93),
    "brown": (0.68, 0.34, 0.16),
    "red": (1.00, 0.20, 0.12),
    "orange": (1.00, 0.48, 0.16),
    "yellow": (1.00, 0.82, 0.34),
    "lime": (0.61, 1.00, 0.22),
    "green": (0.20, 0.92, 0.35),
    "cyan": (0.15, 0.92, 0.89),
    "light_blue": (0.28, 0.70, 1.00),
    "blue": (0.18, 0.34, 1.00),
    "purple": (0.61, 0.26, 1.00),
    "magenta": (1.00, 0.28, 0.80),
    "pink": (1.00, 0.59, 0.76),
}
BLOCK_IDS = {color: 26000 + i for i, color in enumerate(PALETTE)}
ITEM_IDS = {color: 26100 + i for i, color in enumerate(PALETTE)}

# Vanilla seeded sources work even without an optional Euphoria checkout.
VANILLA_BLOCKS = {
    "orange": ["minecraft:fire", "minecraft:lava", "minecraft:torch", "minecraft:wall_torch", "minecraft:lantern",
               "minecraft:campfire:lit=true", "minecraft:shroomlight",
               "minecraft:jack_o_lantern"],
    "blue": ["minecraft:soul_fire", "minecraft:soul_torch", "minecraft:soul_wall_torch",
             "minecraft:soul_lantern", "minecraft:soul_campfire:lit=true"],
    "cyan": ["minecraft:sea_lantern", "minecraft:conduit"],
    "yellow": ["minecraft:glowstone", "minecraft:ochre_froglight"],
    "green": ["minecraft:verdant_froglight"],
    "purple": ["minecraft:pearlescent_froglight", "minecraft:crying_obsidian"],
    "red": ["minecraft:redstone_torch", "minecraft:redstone_wall_torch",
            "minecraft:redstone_lamp:lit=true"],
}
VANILLA_ITEMS = {
    "orange": ["minecraft:torch", "minecraft:lantern", "minecraft:campfire",
               "minecraft:shroomlight", "minecraft:jack_o_lantern"],
    "blue": ["minecraft:soul_torch", "minecraft:soul_lantern",
             "minecraft:soul_campfire"],
    "cyan": ["minecraft:sea_lantern", "minecraft:conduit"],
    "yellow": ["minecraft:glowstone", "minecraft:ochre_froglight"],
    "green": ["minecraft:verdant_froglight"],
    "purple": ["minecraft:pearlescent_froglight", "minecraft:crying_obsidian"],
    "red": ["minecraft:redstone_torch", "minecraft:redstone_lamp"],
}

# Euphoria property IDs are from MIT-licensed 'propertiesFiles', pinned in CI.
# Only these emitter classifications are imported; other IDs are deliberately
# ignored (they cover material properties, foliage and countless nonemitters).
EUPHORIA_BLOCK_ID_TO_COLOR = {21000 + 2 * i: color for i, color in enumerate(PALETTE)}

def shader_prefix(names: list[str]) -> str:
    roots = [n[:-len("shaders/shaders.properties")]
             for n in names if n.endswith("shaders/shaders.properties")]
    if not roots:
        raise ValueError("Input is not an E-Lite shader pack: missing shaders.properties")
    return min(roots, key=len)

def clean_path(name: str) -> str:
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Unsafe ZIP entry: {name!r}")
    return p.as_posix()

def read_source(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as z:
        names = [clean_path(x.filename) for x in z.infolist() if not x.is_dir()]
        prefix = shader_prefix(names)
        result = {}
        for info in z.infolist():
            if info.is_dir():
                continue
            n = clean_path(info.filename)
            if not n.startswith(prefix):
                continue
            dest = n[len(prefix):]
            if dest:
                result[dest] = z.read(info)
    required = ["shaders/src/light_vertex.glsl", "shaders/lib/config.glsl",
                "shaders/common/solid_blocks_vertex.glsl",
                "shaders/common/final_fragment.glsl",
                "shaders/item.properties", "shaders/block.properties"]
    missing = [x for x in required if x not in result]
    if missing:
        raise ValueError("Unexpected E-Lite layout: " + ", ".join(missing))
    return result

def parse_properties(body: str) -> dict[int, list[str]]:
    """Parse OptiFine multiline assignments without losing block-state tokens."""
    logical = re.sub(r"\\\s*\n", " ", body)
    result = defaultdict(list)
    for line in logical.splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^(?:block|item)\.(\d+)\s*=\s*(.*)$", line)
        if m:
            result[int(m[1])].extend(m[2].split())
    return dict(result)

def normalized(token: str) -> str:
    # No colon is vanilla. A colon after the block name can indicate state.
    return token if ":" in token else "minecraft:" + token

def emitter_entries(euphoria_root: Path | None, kind: str) -> dict[str, set[str]]:
    base = VANILLA_BLOCKS if kind == "block" else VANILLA_ITEMS
    groups = {key: set(base.get(key, ())) for key in PALETTE}
    if euphoria_root is None:
        return groups
    if kind == "block":
        paths = sorted((euphoria_root / "blockProperties" / "1.13+").glob("block.*.properties"))
        if not paths:
            raise ValueError("No Euphoria 1.13+ block property fragments found")
        for path in paths:
            prop = parse_properties(path.read_text(encoding="utf-8-sig"))
            for ident, color in EUPHORIA_BLOCK_ID_TO_COLOR.items():
                groups[color].update(prop.get(ident, ()))
    else:
        path = euphoria_root / "item.properties"
        body = path.read_text(encoding="utf-8-sig")
        # Match Euphoria's MIT-licensed 'Modded Light Source - Color' headings.
        for match in re.finditer(
            r"(?im)^\s*#\s*Modded Light Source\s*-\s*([^\n]+)\s*$", body
        ):
            label = match[1].split("-")[0].strip().lower().replace(" ", "_")
            if label not in PALETTE:
                continue
            subsequent = body[match.end():]
            ident = re.search(r"(?m)^\s*item\.(\d+)\s*=", subsequent)
            if not ident:
                continue
            line = subsequent[:ident.end()] + subsequent[ident.end():].split("\n#", 1)[0]
            assignments = parse_properties(line)
            groups[label].update(assignments.get(int(ident[1]), ()))
    for color in PALETTE:
        groups[color] = {x for x in groups[color] if x and not x.startswith("tags_")}
    return groups

def rewrite_property_table(old: str, groups: dict[str, set[str]], kind: str) -> tuple[str, int]:
    """One color per token. Remove exact conflicts from E-Lite old IDs."""
    target = BLOCK_IDS if kind == "block" else ITEM_IDS
    claimed = {}
    for color, members in groups.items():
        for token in sorted(members):
            key = normalized(token)
            # Stable order: earlier source category wins on conflicting inputs.
            claimed.setdefault(key, color)
    lines = []
    for ident, entries in parse_properties(old).items():
        kept = [x for x in entries if normalized(x) not in claimed]
        # Preserve the IDs E-Lite uses for material, waving, etc.
        lines.append(f"{kind}.{ident} = " + " ".join(kept))
    lines += ["", "# MessyShaders RGB classification (Euphoria data used under MIT when supplied)"]
    for color, ident in target.items():
        matches = sorted(t for t, c in claimed.items() if c == color)
        if matches:
            lines.append(f"{kind}.{ident} = " + " ".join(matches))
    return "\n".join(lines) + "\n", len(claimed)

def palette_glsl() -> str:
    s = ["// MessyShaders original 13-tint palette. Vertex-only, no per-pixel loops.",
         "vec3 messyRgbColor(int id) {"]
    for color in PALETTE:
        rgb = PALETTE[color]
        s.append(f"    if (id == {BLOCK_IDS[color]} || id == {ITEM_IDS[color]}) "
                 f"return vec3({rgb[0]:.3f}, {rgb[1]:.3f}, {rgb[2]:.3f});")
    s += ["    return CANDLE_BASELIGHT;", "}"]
    return "\n".join(s) + "\n"

def patch_once(body: str, needle: str, replacement: str, path: str) -> str:
    n = body.count(needle)
    if n != 1:
        raise ValueError(f"Expected one patch anchor in {path}, found {n}: {needle[:75]}")
    return body.replace(needle, replacement, 1)

def apply_overrides(payload: dict[str, bytes], euphoria_root: Path | None) -> dict:
    report = {"shader_base": "E-Lite 5.1.3", "euphoria_mit_catalog": euphoria_root is not None,
              "limitations": ["vertex-approximation only", "no multi-source RGB propagation",
                              "no emitter occlusion", "no IntegratedPBR+ implementation",
                              "no Luxium renderer code"]}
    for kind in ("block", "item"):
        path = f"shaders/{kind}.properties"
        amended, count = rewrite_property_table(
            payload[path].decode("utf-8-sig", "replace"),
            emitter_entries(euphoria_root, kind), kind)
        payload[path] = amended.encode("utf-8")
        report[kind + "_classified"] = count

    payload["shaders/lib/messy_fast_lights.glsl"] = palette_glsl().encode()
    path = "shaders/common/solid_blocks_vertex.glsl"
    body = payload[path].decode("utf-8")
    # The generated palette references CANDLE_BASELIGHT, which expands to
    # normalizeLuma(CANDLE_COLOR, 0.2). E-Lite defines normalizeLuma in
    # lib/luma.glsl, so the palette must be included AFTER that function.
    body = patch_once(body, '#include "/lib/luma.glsl"',
                      '#include "/lib/luma.glsl"\n#include "/lib/messy_fast_lights.glsl"', path)
    payload[path] = body.encode()

    # E-Lite's translucent/water renderer also includes the shared
    # src/light_vertex.glsl. It does not include solid_blocks_vertex.glsl.
    # Both callers must define messyRgbColor, and the helper must follow
    # lib/luma.glsl so CANDLE_BASELIGHT can resolve normalizeLuma.
    path = "shaders/common/water_blocks_vertex.glsl"
    body = payload[path].decode("utf-8")
    body = patch_once(body, '#include "/lib/luma.glsl"',
                      '#include "/lib/luma.glsl"\n#include "/lib/messy_fast_lights.glsl"', path)
    payload[path] = body.encode()

    path = "shaders/src/light_vertex.glsl"
    body = payload[path].decode("utf-8")
    a = body.index("#ifdef DYN_HAND_LIGHT")
    b = body.index("#endif", a) + len("#endif")
    hand = """#ifdef DYN_HAND_LIGHT
    // Two bounded sources; uses E-Lite's existing fake hand-light falloff.
    // Not scene-wide dynamic entity or dropped-item lighting.
    vec3 messyHeld = vec3(0.0);
    float messyDistance = clamp(1.0 - gl_FogFragCoord * 0.0666, 0.0, 1.0);
    float messyFalloff = messyDistance * messyDistance * messyDistance;
    if (heldItemId >= 26100 && heldItemId <= 26112)
        messyHeld += messyRgbColor(heldItemId);
    else if (heldItemId == 11001 || heldItemId == 11002)
        messyHeld += CANDLE_BASELIGHT;
    if (heldItemId2 >= 26100 && heldItemId2 <= 26112)
        messyHeld += messyRgbColor(heldItemId2);
    else if (heldItemId2 == 11001 || heldItemId2 == 11002)
        messyHeld += CANDLE_BASELIGHT;
    candle_color = max(candle_color, messyHeld * messyFalloff * 1.4);
#endif"""
    body = body[:a] + hand + body[b:]
    # Direct self-emission on visible colored block surfaces only. No light
    # propagation is claimed or implied by this early implementation.
    anchor = "#if defined GBUFFER_HAND\n"
    direct = """#if defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK
    if (mc_ex >= 26000 && mc_ex <= 26012)
        candle_color = max(candle_color, messyRgbColor(mc_ex) * 0.85);
#endif

"""
    body = patch_once(body, anchor, direct + anchor, path)
    payload[path] = body.encode()

    # Barely-there original look: slightly cooler shadows, warmer highlights.
    # No extra framebuffer reads or additional rendering pass.
    path = "shaders/common/final_fragment.glsl"
    body = payload[path].decode("utf-8")
    anchor = "block_color = pow(block_color.rgb, vec3(1 / GAMMA));"
    grade = """block_color = pow(block_color.rgb, vec3(1 / GAMMA));
    #ifdef MESSY_TONE
        float messyHighlight = smoothstep(0.22, 0.83, luma(block_color));
        block_color *= mix(vec3(0.975, 1.005, 1.035),
                           vec3(1.028, 1.000, 0.975), messyHighlight);
    #endif"""
    payload[path] = patch_once(body, anchor, grade, path).encode()

    path = "shaders/lib/config.glsl"
    body = payload[path].decode("utf-8")
    payload[path] = ("// MessyShaders: cheap original color grade.\n"
                     "#define MESSY_TONE\n" + body).encode()
    payload["MESSYSHADERS_NOTES.txt"] = (
        "EXPERIMENTAL alpha. E-Lite 5.1.3 LGPL-3.0; retain original source and credits.\n"
        "Euphoria propertiesFiles classifications: copyright SpacEagle17, MIT License;\n"
        "https://github.com/EuphoriaPatches/propertiesFiles\n"
        "Custom palette + adaptation: MessyShaders. Luxium and Complementary are\n"
        "architecture/visual references ONLY. No code from either is included.\n"
        "Block/item RGB, selected moving lights, and texture-generated normals tested offline.\n"
        "NOT yet exact occlusion, complete r5.10 entity parity, full IPBR+, or measured GPU speed.\n"
    ).encode()
    payload["LICENSES/EUPHORIA-PROPERTIES-MIT.txt"] = (ROOT / "licenses" / "EUPHORIA-PROPERTIES-MIT.txt").read_bytes()
    # True spatial RGB light prototype, independent of the fake held-item path.
    try:
        from .patch_world_rgb import apply_world_rgb
    except ImportError:
        from patch_world_rgb import apply_world_rgb
    report["world_rgb"] = apply_world_rgb(payload)
    # Drop/item/entity light emitters and shader-side generated PBR.
    try:
        from .patch_dynamic_ipbr import apply_dynamic_ipbr
    except ImportError:
        from patch_dynamic_ipbr import apply_dynamic_ipbr
    report["dynamic_ipbr"] = apply_dynamic_ipbr(payload)
    try:
        from .patch_coverage_coating import patch_full_coverage_coating
    except ImportError:
        from patch_coverage_coating import patch_full_coverage_coating
    report["coverage_coating"] = patch_full_coverage_coating(payload, euphoria_root)
    # Use one temporal RGB image pair for all three render paths, and
    # expose native Voxy/Colorwheel bridges in the same shader archive.
    try:
        from .patch_temporal_compat import apply_temporal_normals
    except ImportError:
        from patch_temporal_compat import apply_temporal_normals
    report["temporal_normals"] = apply_temporal_normals(payload)
    try:
        from .patch_render_compat import apply_render_compat
    except ImportError:
        from patch_render_compat import apply_render_compat
    report["render_compatibility"] = apply_render_compat(payload)
    report["limitations"] = [
        "Prototype 48-cubed nearby volume, six diffusion steps; not performance-tested",
        "Approximate voxel occlusion; thin/translucent block correctness pending",
        "Light sources collected from shadow geometry, not all loaded chunks",
        "Only shadow-rendered item and selected entity sources tracked; not all entity types",
        "Dynamic RGB is not yet guaranteed correct for every modded emitter",
        "Procedural PBR approximation; no full Complementary IntegratedPBR+ parity",
        "No Luxium renderer code",
    ]
    payload["MESSYSHADERS_BUILD.json"] = json.dumps(report, indent=2).encode()
    return report

def build(source: Path, output: Path, euphoria_root: Path | None) -> dict:
    payload = read_source(source)
    info = apply_overrides(payload, euphoria_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as out:
        for path, data in sorted(payload.items()):
            z = ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            z.compress_type = ZIP_DEFLATED
            z.external_attr = 0o644 << 16
            out.writestr(z, data)
    with ZipFile(output) as check:
        if check.testzip() is not None:
            raise RuntimeError("ZIP CRC failure")
        if "shaders/shaders.properties" not in check.namelist():
            raise RuntimeError("Shader root is missing")
    info["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    info["output"] = str(output)
    return info

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=SOURCE)
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--euphoria-root", type=Path, default=None)
    args = p.parse_args()
    print(json.dumps(build(args.source, args.output, args.euphoria_root), indent=2))

if __name__ == "__main__":
    main()
